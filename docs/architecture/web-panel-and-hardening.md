# Painel do Professor em React e Hardening de Segurança (Etapa 9)

Documentação arquitetural do painel web administrativo do professor e dos ensaios de segurança e hardening do UniCode.

---

## 1. Visão Geral da Arquitetura

O painel administrativo do professor foi implementado seguindo o princípio do menor privilégio:

```
 Professor (Browser) ──HTTP──► Uvicorn / FastAPI (:8000)
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
       SPA React (web/dist)              API REST (/api/*)
       (HTML, JS, CSS, Assets)                   │
                                                 │ HTTP Basic (Email + Senha)
                                                 ▼
                                        PostgreSQL 16
                                        • Papel: unicode_panel
                                        • Apenas SELECT
                                        • Sem acesso à tabela sessions
```

- **Backend:** FastAPI expõe uma API REST sob `/api/*`, conectando-se ao PostgreSQL exclusivamente através do papel `unicode_panel` (`SELECT` apenas, sem acesso a sessões de alunos ou permissão de escrita).
- **Autenticação:** HTTP Basic com Email (`UNICODE_ADMIN_EMAIL`) e Senha (`UNICODE_ADMIN_PASSWORD`), comparados em tempo constante (`secrets.compare_digest`). Em caso de falha, retorna `401 Unauthorized` com JSON sem o header `WWW-Authenticate`, evitando pop-ups nativos do navegador sobre o SPA.
- **Frontend SPA:** Aplicação React 19 + TypeScript + Vite + Tailwind CSS localizada em `web/`, servida na mesma porta pelo próprio FastAPI através do diretório `web/dist/` (configurável via `UNICODE_WEB_DIST_DIR`).
- **CLI Administrativo:** Adicionado o comando `unicode-admin export-notas <unidade> [--turma <turma>] [--output <arquivo.csv>]` para exportar o mesmo CSV gerado pelo painel diretamente do terminal.
- **CLI Web:** Criado o entrypoint `unicode-web [--host <host>] [--port <port>]` para subir o servidor Uvicorn facilmente.

---

## 2. Invariantes de Hardening & Segurança

Os testes em `tests/test_e2e_hardening.py` garantem as seguintes propriedades:

1. **Proteção Contra Força Bruta no Login:**
   - O login do aluno via SSH (`unicode-login`) bloqueia requisições após 5 falhas no mesmo IP dentro de uma janela de tempo (60 segundos).
   - As respostas de erro são sempre genéricas ("credenciais inválidas"), impedindo a enumeração de matrículas ou emails válidos.
2. **Não-Vazamento de Testes Ocultos:**
   - O feedback retornado pela submissão (`StudentFeedback` / `format_submit_output`) informa apenas status, contagem de testes aprovados/totais e o nome do primeiro teste que falhou.
   - O código-fonte dos testes ocultos (`test_eval.py`), asserções internas e saídas diagnósticas completas nunca chegam ao workspace ou ao terminal do aluno.
3. **Limite e Atomicidade de Tentativas:**
   - Toda tentativa é registrada no banco como `running` antes de rodar os testes na sandbox.
   - Submissões em questões já aprovadas (`passed`) ou esgotadas (`exhausted`) são estritamente rejeitadas.
4. **Isolamento de Banco do Papel `unicode_panel`:**
   - O papel PostgreSQL `unicode_panel` tem permissão concedida apenas para `SELECT` nas tabelas `students`, `units`, `questions`, `assignments`, `attempts`, `audit_log` e na view `grades_by_unit`.
   - Tentativas de ler `sessions` ou executar `INSERT`, `UPDATE` ou `DELETE` são rejeitadas com erro de permissão insuficiente (`psycopg.errors.InsufficientPrivilege`).

