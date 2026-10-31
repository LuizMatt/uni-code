# Sandbox de Execução e Serviço de Submissão

Especificação técnica do executor isolado de testes (`unicode-sandbox` / `unicode.sandbox.runner`) e do ciclo transacional de submissões (`unicode.services.submissions`).

---

## 1. Visão Geral

Cada submissão de código passa por três fases desacopladas para garantir atomicidade contábil e isolamento de segurança:

1. **Fase A (`reserve_attempt` — Transação curta no PostgreSQL):**
   Bloqueia o sorteio ativo do aluno (`FOR UPDATE OF a`), valida elegibilidade (`state = 'pending'`, nenhuma tentativa `running` em andamento, menos de 3 tentativas realizadas) e insere a tentativa com `status = 'running'`. O `COMMIT` ocorre antes de iniciar qualquer container.
2. **Fase B (`DockerSandboxRunner.run` — Fora de transação):**
   Executa a suíte oculta `test_eval.py` contra o código submetido (`solution.py`) dentro de um container Docker efêmero e restrito, sem manter conexões ou locks abertos no PostgreSQL.
3. **Fase C (`finalize_attempt` — Transação curta no PostgreSQL):**
   Grava o resultado na tabela `attempts`, aplica a regra tudo-ou-nada na tabela `assignments` (`0.5` pontos somente se `tests_passed == tests_total` e `tests_total > 0`; `exhausted` na 3ª tentativa sem aprovação), registra auditoria em `audit_log` e retorna um `StudentFeedback` sanitizado.

---

## 2. Sandbox de Testes (`docker/sandbox/` e `src/unicode/sandbox/runner.py`)

### Construção da Imagem

```powershell
docker build -t unicode-sandbox docker/sandbox
```

### Garantias de Isolamento do Container

| Flag Docker | Valor | Propósito |
|---|---|---|
| `--network` | `none` | Bloqueia qualquer acesso de rede externa ou local |
| `--read-only` | ativo | Raiz do container em modo somente leitura |
| `--cap-drop` | `ALL` | Remove todas as capabilities Linux do processo |
| `--security-opt` | `no-new-privileges` | Impede escalonamento de privilégios via setuid/setgid |
| `--pids-limit` | `64` (`UNICODE_SANDBOX_PIDS_LIMIT`) | Previne fork bombs |
| `--memory` / `--memory-swap` | `256m` (`UNICODE_SANDBOX_MEMORY_MB`) | Limite rígido de RAM sem swap |
| `--cpus` | `0.5` (`UNICODE_SANDBOX_CPUS`) | Limite de uso de CPU |
| `--user` | `65534:65534` (`nobody`) | Execução sem privilégios |
| `--tmpfs` | `/tmp:rw,noexec,nosuid,size=16m,mode=1777` | Único diretório gravável em memória para arquivos temporários do pytest |
| `-v <tmp>:/workspace:ro` | somente leitura | Monta apenas `solution.py` e `test_eval.py` |

### Extração Segura do Relatório (`sandbox_entry.py`)

O entrypoint do container executa o `pytest` em um **subprocesso filho** com `python -I` e `timeout` de `UNICODE_SANDBOX_TIMEOUT_SECONDS` (padrão: `5` segundos), gravando o relatório JSON em `/tmp/report-<token>.json`. Somente após o término completo do processo filho, o `sandbox_entry.py` lê o relatório e emite um envelope JSON estruturado para o host. No bloco `finally`, o host sempre executa `docker rm -f <container_name>`.

---

## 3. Recuperação de Falhas (`recover_stale_attempts`)

Caso o processo do daemon sofra queda ou reinício entre a Fase A e a Fase C:
- Ao iniciar, o daemon invoca `recover_stale_attempts(conn)`.
- Tentativas presas em `status = 'running'` são marcadas como `status = 'error'` (`tests_total = 0`, `tests_passed = 0`, `finished_at = now()`), permanecendo contabilizadas.
- Se a tentativa recuperada for a 3ª tentativa (`number = 3`) de um sorteio ainda `pending`, o sorteio é atualizado para `state = 'exhausted'` (`points = 0`).

---

## 4. Feedback Sanitizado vs Diagnóstico do Professor

- **`attempts.output` (Banco de Dados):** Armazena o `diagnostic_output` completo (tracebacks curtos e erros de coleta) para consulta do professor e auditoria.
- **`StudentFeedback` (Retorno ao Aluno):** Contém exclusivamente `status`, `tests_total`, `tests_passed`, `attempt_number`, `attempts_remaining`, `assignment_state`, `points`, `first_failed_test` (apenas o nome da função de teste) e `error_category` (ex.: `SyntaxError`, `TimeoutError`, `MemoryError`), sem jamais expor o código ou valores dos asserts de `test_eval.py`.
