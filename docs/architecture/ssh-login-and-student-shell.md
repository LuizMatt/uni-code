# Login SSH (`unicode-login`) e Shell do Aluno (`unicode-aluno-shell`)

Especificação do fluxo de entrada via SSH, autenticação com tempo constante e rate limit por IP, provisionamento do workspace e isolamento do container interativo do aluno.

---

## 1. Fluxo de Autenticação (`unicode-login`)

1. **Entrada via `sshd` (`ForceCommand`):**
   - Todos os alunos conectam via SSH com o usuário compartilhado `aluno`.
   - O `sshd` (configurado via `docker/aluno-shell/sshd_config`) bloqueia encaminhamento TCP/X11/túneis/agente e força a execução de `/usr/local/bin/unicode-login`.
2. **Extração de IP e Rate Limit (`authenticate_student_login`):**
   - O IP de origem é extraído de `SSH_CONNECTION` ou `SSH_CLIENT` (`extract_client_ip`).
   - Um advisory lock transacional (`pg_advisory_xact_lock(hashtext('login_ip'), hashtext(ip))`) serializa tentativas simultâneas da mesma origem.
   - Se o IP possuir `>= 5` registros `action = 'login_failed'` em `audit_log` nos últimos `60` segundos, a tentativa é rejeitada imediatamente com `LoginRateLimitError` e auditada como `login_rate_limited`.
3. **Comparação em Tempo Constante:**
   - `email` (normalizado em minúsculas) e `registration` têm seus digests SHA-256 de 32 bytes comparados com `secrets.compare_digest` (mesmo quando a matrícula não é encontrada, comparando contra digests vazios para evitar canal lateral de tempo).
   - Qualquer falha grava `login_failed` em `audit_log` (comitado no banco) e imprime exclusivamente `"Erro: credenciais inválidas."`.
4. **Sessão, Workspace e Revogação no Logout:**
   - Em caso de sucesso, `create_session` emite o token de sessão (`UNICODE_SESSION`), `login` é registrado em `audit_log`, e `ensure_student_workspace` garante `/srv/unicode/workspaces/<matricula>` e os arquivos (`README.md`, `solution.py`) de eventuais sorteios ativos.
   - O container `unicode-aluno-shell` é iniciado anexado ao terminal do aluno.
   - Assim que o container encerra, o bloco `finally` do `unicode-login` revoga o token em `sessions` (`revoke_session`) e grava `logout` em `audit_log`.

---

## 2. Isolamento do Container (`unicode-aluno-shell`)

Construção da imagem a partir da raiz do repositório:

```bash
docker build -f docker/aluno-shell/Dockerfile -t unicode-aluno-shell .
```

- O arquivo `.dockerignore` garante que `questions/`, `workspaces/` e `.env` nunca façam parte do contexto de build.
- Execução pelo `unicode-login`:
  - `--rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges`
  - `--pids-limit 128 --memory 512m --memory-swap 512m --cpus 1.0 --user 1000:1000`
  - `--tmpfs /tmp:rw,noexec,nosuid,size=64m,mode=1777`
  - `-v /srv/unicode/workspaces/<matricula>:/home/aluno:rw`
  - `-v /run/unicode/daemon.sock:/run/unicode/daemon.sock:rw`
  - `-e UNICODE_SESSION=<token> -e UNICODE_DAEMON_SOCKET_PATH=/run/unicode/daemon.sock -e UNICODE_STUDENT_WORKSPACE_DIR=/home/aluno`

---

## 3. Permissões e Requisitos no Host (Produção)

O usuário Linux compartilhado `aluno` no host executa o `ForceCommand /usr/local/bin/unicode-login`. Para seu correto funcionamento:
1. **Grupo `docker`:** O usuário `aluno` deve pertencer ao grupo `docker` no host para conseguir invocar `docker run` sem `sudo`.
2. **Diretório de Workspaces (`/srv/unicode/workspaces`):** O diretório base deve permitir escrita pelo usuário `aluno` (ex.: dono `aluno:aluno` ou permissão `0770`), permitindo que `ensure_student_workspace` crie a pasta `/srv/unicode/workspaces/<matricula>`.
3. **Socket do Daemon (`/run/unicode/daemon.sock`):** Criado com permissão `0660` e grupo compartilhado com o daemon para leitura e escrita pelo `unicode-login` e pelos containers.
