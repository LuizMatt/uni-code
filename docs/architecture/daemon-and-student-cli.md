# Daemon (`unicode-daemon`) e CLI do Aluno (`unicode`)

Especificação técnica do servidor de comunicação IPC (`unicode.daemon`), do gerenciamento de sessões (`unicode.services.sessions`) e da CLI utilizada pelo aluno dentro do container (`unicode.cli_student`).

---

## 1. Autenticação de Sessões (`sessions`)

- Na criação da sessão (`create_session`), um token criptográfico aleatório (`secrets.token_urlsafe(32)`) é emitido.
- O banco armazena **apenas o hash SHA-256 de 32 bytes** (`sessions.token_hash`). O token puro nunca é gravado em disco ou no PostgreSQL.
- Cada chamada IPC da CLI `unicode` lê o token da variável de ambiente `UNICODE_SESSION` e o envia no envelope da requisição.
- O `unicode-daemon` autentica o token via `authenticate_session(conn, token)` (`token_hash = sha256(token)` e `expires_at > now()`) e deriva a matrícula (`student_registration`) diretamente da sessão.

---

## 2. Protocolo IPC (`unicode.daemon.protocol`)

O protocolo utiliza mensagens JSON delimitadas por quebra de linha (`\n`, máximo de 256 KB por mensagem) sobre sockets stream:

- **Produção (Linux):** Unix Domain Socket em `UNICODE_DAEMON_SOCKET_PATH` (padrão `/run/unicode/daemon.sock`, permissão `0660`).
- **Desenvolvimento / Testes Locais:** Suporte a endpoints `tcp://127.0.0.1:<porta>`.

### Requisição
```json
{
  "token": "<UNICODE_SESSION>",
  "action": "start | status | submit",
  "payload": {}
}
```

### Resposta
- **Sucesso:** `{"ok": true, "data": { ... }}`
- **Erro:** `{"ok": false, "error": {"code": "auth_error | not_found | business_error | invalid_request | internal_error", "message": "..."}}`

No startup (`initialize_daemon_state`), o daemon executa `recover_stale_attempts(conn)` e `cleanup_expired_sessions(conn)` antes de abrir o socket para conexões.

---

## 3. Comandos da CLI do Aluno (`unicode`)

### `unicode start <unidade>`
Realiza o sorteio idempotente das 2 questões da unidade (ou recupera o sorteio ativo) e provisiona `<unidade>/<questao>/README.md` e `solution.py` no workspace do aluno.

### `unicode status [--unidade / -u <unidade>]`
Exibe a tabela de questões sorteadas por unidade com título, estado (`pendente`, `aprovada`, `esgotada`), tentativas usadas/restantes (`usadas/3 (restantes)`) e nota parcial.

### `unicode submit [questao] [--unidade / -u <unidade>] [--arquivo / -f <caminho>]`
Envia o conteúdo de `solution.py` ao daemon, executa a avaliação na sandbox isolada (consumindo 1 tentativa) e imprime exclusivamente o `StudentFeedback` sanitizado.

### `unicode test [questao] [--unidade / -u <unidade>] [--arquivo / -f <caminho>]`
Executa localmente (com `python -I`, sem rede com o daemon e **sem consumir tentativa**) os exemplos públicos de `assert` contidos nos blocos ```` ```python ```` do `README.md` da questão contra o `solution.py` do aluno.
