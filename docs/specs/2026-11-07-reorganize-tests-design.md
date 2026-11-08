# Design: Reorganização da Estrutura de Testes

**Data:** 2026-11-07  
**Branch:** `feat/organize-tests`  
**Status:** Aprovado  

---

## 1. Contexto e Motivação

Atualmente, o diretório `tests/` do UniCode contém mais de 30 arquivos de teste planos na raiz, misturando testes unitários de modelos, serviços de regras de negócio, interfaces de linha de comando (CLI), servidores daemon, isolamento de sandbox, rotas web FastAPI e testes de infraestrutura/banco de dados.

Essa falta de hierarquia dificulta:
1. Encontrar rapidamente o teste correspondente a um módulo de `src/unicode/`.
2. Executar suítes específicas (ex: rodar apenas testes de modelos ou apenas testes de serviços durante o ciclo de desenvolvimento rápido).
3. Manter a legibilidade e escalabilidade do projeto.

---

## 2. Objetivos e Não-Objetivos

### Objetivos
- Reorganizar os arquivos de teste em subdiretórios que espelhem a arquitetura modular do código em `src/unicode/`.
- Criar pastas dedicadas para testes transversais (`infra/` e `e2e/`).
- Simplificar os nomes dos arquivos para evitar redundâncias agora que estão sob pastas categorizadas (ex: `tests/models/test_student.py` em vez de `test_student_models.py`).
- Garantir que `tests/conftest.py` e `tests/support.py` permaneçam acessíveis sem quebrar imports existentes (`from tests.support import ...`).
- Adicionar `__init__.py` nas novas subpastas para suporte transparente ao `mypy` e ao coletor do `pytest`.
- Garantir que a suíte de testes (`pytest`), o linter (`ruff`) e a checagem de tipos (`mypy`) continuem passando sem alterações lógicas no código de teste.

### Não-Objetivos
- Não haverá refatoração lógica do código interno dos testes (apenas movimentação de arquivos).
- Não haverá unificação/fusão de testes distintos em arquivos únicos.
- Não haverá alteração no código fonte em `src/unicode/`.

---

## 3. Estrutura Proposta e Mapeamento de Arquivos

### 3.1 Raiz de Testes
- `tests/conftest.py`: Fixtures compartilhadas de sessão e banco de dados.
- `tests/support.py`: Constantes de conexão de teste (`TEST_OWNER_URL`, etc.) e utilitários auxiliares.
- `tests/__init__.py`: Marcação da raiz de testes como pacote Python.

### 3.2 Mapeamento 1:1 dos Arquivos

| Arquivo Atual (`tests/`) | Novo Caminho | Categoria |
| :--- | :--- | :--- |
| `test_assignment_models.py` | `tests/models/test_assignment.py` | Models |
| `test_attempt_models.py` | `tests/models/test_attempt.py` | Models |
| `test_question_models.py` | `tests/models/test_question.py` | Models |
| `test_student_models.py` | `tests/models/test_student.py` | Models |
| `test_assignments.py` | `tests/services/test_assignments.py` | Services |
| `test_grades.py` | `tests/services/test_grades.py` | Services |
| `test_sessions.py` | `tests/services/test_sessions.py` | Services |
| `test_submissions.py` | `tests/services/test_submissions.py` | Services |
| `test_workspace.py` | `tests/services/test_workspace.py` | Services |
| `test_import_students.py` | `tests/services/test_students_import.py` | Services |
| `test_list_students.py` | `tests/services/test_students_list.py` | Services |
| `test_csv_parser.py` | `tests/services/test_csv_parser.py` | Services |
| `test_sync_questions.py` | `tests/services/test_questions_sync.py` | Services |
| `test_question_scanner.py` | `tests/services/test_question_scanner.py` | Services |
| `test_cli_admin.py` | `tests/cli/test_admin.py` | CLI |
| `test_cli_admin_format.py` | `tests/cli/test_admin_format.py` | CLI |
| `test_cli_admin_grades.py` | `tests/cli/test_admin_grades.py` | CLI |
| `test_cli_admin_questions.py` | `tests/cli/test_admin_questions.py` | CLI |
| `test_cli_admin_reset.py` | `tests/cli/test_admin_reset.py` | CLI |
| `test_cli_student.py` | `tests/cli/test_student.py` | CLI |
| `test_daemon.py` | `tests/daemon/test_daemon.py` | Daemon |
| `test_sandbox_runner.py` | `tests/sandbox/test_runner.py` | Sandbox |
| `test_sandbox_integration.py` | `tests/sandbox/test_integration.py` | Sandbox |
| `test_web_api.py` | `tests/web/test_api.py` | Web |
| `test_web_frontend_structure.py` | `tests/web/test_frontend_structure.py` | Web |
| `test_db.py` | `tests/infra/test_db.py` | Infra |
| `test_migrations.py` | `tests/infra/test_migrations.py` | Infra |
| `test_schema.py` | `tests/infra/test_schema.py` | Infra |
| `test_grants.py` | `tests/infra/test_grants.py` | Infra |
| `test_config.py` | `tests/infra/test_config.py` | Infra |
| `test_login.py` | `tests/infra/test_login.py` | Infra |
| `test_e2e_hardening.py` | `tests/e2e/test_hardening.py` | E2E |

---

## 4. Pacotes e Suporte a Ferramentas

1. **Imports Python:**
   - Todos os arquivos de teste que importam `from tests.support import ...` mantêm a sintaxe idêntica, pois a pasta raiz continua sendo `tests`.
   - Cada subdiretório conterá um `__init__.py` vazio para que o Python e o `mypy` considerem os subpacotes como módulos regulares (`tests.models`, `tests.services`, etc.).

2. **Ferramental (`pyproject.toml`):**
   - **Pytest:** `testpaths = ["tests"]` continuará descobrindo automaticamente todos os arquivos que iniciam com `test_*.py` recursivamente.
   - **Mypy:** A configuração `packages = ["unicode", "tests"]` resolverá os novos subpacotes sem colisões.
   - **Ruff:** A checagem de estilo e imports com `src = ["src", "tests"]` funcionará em toda a árvore.

---

## 5. Estratégia de Validação

A validação da reorganização será executada nas seguintes etapas:
1. **Verificação de tipos:** `uv run mypy` deve retornar 0 erros.
2. **Lint e formatação:** `uv run ruff check` deve validar todos os arquivos movidos.
3. **Execução de testes:** `uv run pytest -q` para garantir que todas as suítes continuam sendo descobertas e executadas sem falhas de importação ou path relativo.
