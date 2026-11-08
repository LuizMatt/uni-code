# Plano de Implementação: Reorganização da Estrutura de Testes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganizar todos os 32 arquivos de teste atualmente planos em `tests/` em subpastas modulares (`models/`, `services/`, `cli/`, `daemon/`, `sandbox/`, `web/`, `infra/`, `e2e/`), simplificando os nomes dos arquivos e mantendo intacta a compatibilidade com `pytest`, `mypy` e `ruff`.

**Architecture:** Espelhamento 1:1 dos módulos de `src/unicode/` com adição de pastas transversais para infraestrutura (`infra/`) e testes de ponta a ponta (`e2e/`). Uso de `git mv` para preservar o histórico do git e adição de `__init__.py` em cada nova subpasta.

**Tech Stack:** Python 3.12, Pytest, Mypy, Ruff, Git.

## Global Constraints

- Todos os arquivos de teste que importam `from tests.support import ...` devem continuar funcionando sem qualquer alteração sintática.
- `tests/conftest.py` e `tests/support.py` permanecem na raiz de `tests/`.
- Todos os comandos git que alterem o índice devem preservar histórico via `git mv`.
- A cada tarefa, executar validação com `pytest` na subpasta correspondente antes de commitar.
- `uv run ruff check` e `uv run mypy` devem passar sem erros ao término de todas as movimentações.

---

### Task 1: Criar diretórios de teste e arquivos `__init__.py`

**Files:**
- Create: `tests/models/__init__.py`
- Create: `tests/services/__init__.py`
- Create: `tests/cli/__init__.py`
- Create: `tests/daemon/__init__.py`
- Create: `tests/sandbox/__init__.py`
- Create: `tests/web/__init__.py`
- Create: `tests/infra/__init__.py`
- Create: `tests/e2e/__init__.py`

- [ ] **Step 1: Criar as pastas e arquivos `__init__.py` vazios**

Executar criação dos arquivos `__init__.py` vazios em cada um dos subdiretórios planejados.

- [ ] **Step 2: Verificar criação dos diretórios**

Executar: `Get-ChildItem -Directory tests`
Esperado: Lista com `cli`, `daemon`, `e2e`, `infra`, `models`, `sandbox`, `services`, `web`.

- [ ] **Step 3: Commit**

```bash
git add tests/models/__init__.py tests/services/__init__.py tests/cli/__init__.py tests/daemon/__init__.py tests/sandbox/__init__.py tests/web/__init__.py tests/infra/__init__.py tests/e2e/__init__.py
git commit -m "chore(tests): scaffold package directories and __init__.py files"
```

---

### Task 2: Mover e renomear testes de `models/`

**Files:**
- Move: `tests/test_assignment_models.py` -> `tests/models/test_assignment.py`
- Move: `tests/test_attempt_models.py` -> `tests/models/test_attempt.py`
- Move: `tests/test_question_models.py` -> `tests/models/test_question.py`
- Move: `tests/test_student_models.py` -> `tests/models/test_student.py`

- [ ] **Step 1: Mover os arquivos via git mv**

```bash
git mv tests/test_assignment_models.py tests/models/test_assignment.py
git mv tests/test_attempt_models.py tests/models/test_attempt.py
git mv tests/test_question_models.py tests/models/test_question.py
git mv tests/test_student_models.py tests/models/test_student.py
```

- [ ] **Step 2: Executar testes de models**

Executar: `uv run pytest tests/models/ -v`
Esperado: PASS em todos os testes de `tests/models/`.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(tests): move model tests to tests/models/"
```

---

### Task 3: Mover e renomear testes de `services/`

**Files:**
- Move: `tests/test_assignments.py` -> `tests/services/test_assignments.py`
- Move: `tests/test_grades.py` -> `tests/services/test_grades.py`
- Move: `tests/test_sessions.py` -> `tests/services/test_sessions.py`
- Move: `tests/test_submissions.py` -> `tests/services/test_submissions.py`
- Move: `tests/test_workspace.py` -> `tests/services/test_workspace.py`
- Move: `tests/test_import_students.py` -> `tests/services/test_students_import.py`
- Move: `tests/test_list_students.py` -> `tests/services/test_students_list.py`
- Move: `tests/test_csv_parser.py` -> `tests/services/test_csv_parser.py`
- Move: `tests/test_sync_questions.py` -> `tests/services/test_questions_sync.py`
- Move: `tests/test_question_scanner.py` -> `tests/services/test_question_scanner.py`

- [ ] **Step 1: Mover os arquivos via git mv**

```bash
git mv tests/test_assignments.py tests/services/test_assignments.py
git mv tests/test_grades.py tests/services/test_grades.py
git mv tests/test_sessions.py tests/services/test_sessions.py
git mv tests/test_submissions.py tests/services/test_submissions.py
git mv tests/test_workspace.py tests/services/test_workspace.py
git mv tests/test_import_students.py tests/services/test_students_import.py
git mv tests/test_list_students.py tests/services/test_students_list.py
git mv tests/test_csv_parser.py tests/services/test_csv_parser.py
git mv tests/test_sync_questions.py tests/services/test_questions_sync.py
git mv tests/test_question_scanner.py tests/services/test_question_scanner.py
```

- [ ] **Step 2: Executar testes de services**

Executar: `uv run pytest tests/services/ -m "not db and not docker" -v`
Esperado: PASS em todos os testes unitários de serviços.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(tests): move service tests to tests/services/"
```

---

### Task 4: Mover e renomear testes de `cli/`

**Files:**
- Move: `tests/test_cli_admin.py` -> `tests/cli/test_admin.py`
- Move: `tests/test_cli_admin_format.py` -> `tests/cli/test_admin_format.py`
- Move: `tests/test_cli_admin_grades.py` -> `tests/cli/test_admin_grades.py`
- Move: `tests/test_cli_admin_questions.py` -> `tests/cli/test_admin_questions.py`
- Move: `tests/test_cli_admin_reset.py` -> `tests/cli/test_admin_reset.py`
- Move: `tests/test_cli_student.py` -> `tests/cli/test_student.py`

- [ ] **Step 1: Mover os arquivos via git mv**

```bash
git mv tests/test_cli_admin.py tests/cli/test_admin.py
git mv tests/test_cli_admin_format.py tests/cli/test_admin_format.py
git mv tests/test_cli_admin_grades.py tests/cli/test_admin_grades.py
git mv tests/test_cli_admin_questions.py tests/cli/test_admin_questions.py
git mv tests/test_cli_admin_reset.py tests/cli/test_admin_reset.py
git mv tests/test_cli_student.py tests/cli/test_student.py
```

- [ ] **Step 2: Executar testes de CLI**

Executar: `uv run pytest tests/cli/ -m "not db" -v`
Esperado: PASS em todos os testes unitários de CLI.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(tests): move CLI tests to tests/cli/"
```

---

### Task 5: Mover testes de `daemon/`, `sandbox/` e `web/`

**Files:**
- Move: `tests/test_daemon.py` -> `tests/daemon/test_daemon.py`
- Move: `tests/test_sandbox_runner.py` -> `tests/sandbox/test_runner.py`
- Move: `tests/test_sandbox_integration.py` -> `tests/sandbox/test_integration.py`
- Move: `tests/test_web_api.py` -> `tests/web/test_api.py`
- Move: `tests/test_web_frontend_structure.py` -> `tests/web/test_frontend_structure.py`

- [ ] **Step 1: Mover os arquivos via git mv**

```bash
git mv tests/test_daemon.py tests/daemon/test_daemon.py
git mv tests/test_sandbox_runner.py tests/sandbox/test_runner.py
git mv tests/test_sandbox_integration.py tests/sandbox/test_integration.py
git mv tests/test_web_api.py tests/web/test_api.py
git mv tests/test_web_frontend_structure.py tests/web/test_frontend_structure.py
```

- [ ] **Step 2: Executar testes de daemon, sandbox e web**

Executar: `uv run pytest tests/daemon/ tests/sandbox/ tests/web/ -m "not db and not docker" -v`
Esperado: PASS nos testes unitários das 3 pastas.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(tests): move daemon, sandbox, and web tests"
```

---

### Task 6: Mover testes de `infra/` e `e2e/`

**Files:**
- Move: `tests/test_db.py` -> `tests/infra/test_db.py`
- Move: `tests/test_migrations.py` -> `tests/infra/test_migrations.py`
- Move: `tests/test_schema.py` -> `tests/infra/test_schema.py`
- Move: `tests/test_grants.py` -> `tests/infra/test_grants.py`
- Move: `tests/test_config.py` -> `tests/infra/test_config.py`
- Move: `tests/test_login.py` -> `tests/infra/test_login.py`
- Move: `tests/test_e2e_hardening.py` -> `tests/e2e/test_hardening.py`

- [ ] **Step 1: Mover os arquivos via git mv**

```bash
git mv tests/test_db.py tests/infra/test_db.py
git mv tests/test_migrations.py tests/infra/test_migrations.py
git mv tests/test_schema.py tests/infra/test_schema.py
git mv tests/test_grants.py tests/infra/test_grants.py
git mv tests/test_config.py tests/infra/test_config.py
git mv tests/test_login.py tests/infra/test_login.py
git mv tests/test_e2e_hardening.py tests/e2e/test_hardening.py
```

- [ ] **Step 2: Executar testes de infra e e2e**

Executar: `uv run pytest tests/infra/ tests/e2e/ -m "not db" -v`
Esperado: PASS nos testes não dependentes de Postgres externo.

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor(tests): move infra and e2e tests"
```

---

### Task 7: Validação Final com Ruff e Mypy

**Files:**
- Modify (opcional se necessário para documentação): `README.md` ou `CLAUDE.md`

- [ ] **Step 1: Verificar se restou algum arquivo solto na raiz de tests/**

Executar: `Get-ChildItem -File tests`
Esperado: Apenas `conftest.py`, `support.py` e `__init__.py`.

- [ ] **Step 2: Executar linter Ruff**

Executar: `uv run ruff check src tests`
Esperado: All checks passed!

- [ ] **Step 3: Executar verificador de tipos Mypy**

Executar: `uv run mypy`
Esperado: Success: no issues found.

- [ ] **Step 4: Executar suíte pytest completa (sem db/docker)**

Executar: `uv run pytest -m "not db and not docker" -q`
Esperado: Todos os testes coletados e executados com sucesso.

- [ ] **Step 5: Commit final de limpeza/documentação (se houver)**

```bash
git status
```
Se houver pequenas atualizações documentais em `CLAUDE.md`:
```bash
git add CLAUDE.md
git commit -m "docs: update test directory structure in architecture notes"
```
