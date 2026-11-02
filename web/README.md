# UniCode — Painel do Professor (Web Frontend)

Single Page Application (SPA) em **React 19 + TypeScript + Vite + Tailwind CSS** para acompanhamento de notas, submissões e métricas das avaliações do UniCode.

---

## 1. Rotas do Frontend (React Router)

| Rota | Página / Componente | O que faz / Finalidade |
|---|---|---|
| `/login` | `LoginPage` | Tela de autenticação para o professor via Email e Senha (compara em tempo constante com `UNICODE_ADMIN_EMAIL` e `UNICODE_ADMIN_PASSWORD`). Salva a credencial HTTP Basic no `sessionStorage`. |
| `/` | `OverviewPage` | **Visão Geral:** exibe cards de métricas globais (total de alunos, submissões hoje, questões ativas e taxa de aprovação) e a tabela de unidades com botão de exportar CSV de cada uma. |
| `/alunos` | `StudentsPage` | **Listagem de Alunos:** tabela com busca em tempo real (por nome, email ou matrícula), filtro por turma, nota individual em cada unidade e nota total acumulada. Permite navegar direto ao histórico de cada aluno. |
| `/alunos/:matricula` | `StudentDetailPage` | **Histórico do Aluno:** dados cadastrais, pontuação por unidade e lista completa de questões sorteadas (`assignments` ativos e substituídos por reset). Exibe cada tentativa realizada (`1/3`, `2/3`, `3/3`), status, testes que passaram e modal para inspecionar o código snapshot (`solucao.py`) e a saída dos testes. |
| `/unidades/:codigo` | `UnitDetailPage` | **Métricas da Unidade:** detalhamento de cada questão cadastrada, taxa de acerto percentual com barra visual, quantidade de aprovações, esgotamentos e média de tentativas por questão, além de botão para download do CSV de notas da unidade. |

---

## 2. Endpoints da API Backend Consumidos (`FastAPI`)

Todos os endpoints sob `/api/*` requerem cabeçalho `Authorization: Basic <base64(email:senha)>`:

| Método e Endpoint | Descrição | Resposta |
|---|---|---|
| `GET /api/auth/me` | Valida credenciais no login | `{"email": "admin@unicode.local"}` ou `401 Unauthorized` |
| `GET /api/overview` | Estatísticas gerais e lista de unidades | `{"stats": OverviewStats, "units": [UnitSummary]}` |
| `GET /api/students` | Alunos com notas consolidadas (aceita `?unit=...&class_group=...`) | `{"students": [StudentGradesSummary]}` |
| `GET /api/students/{registration}` | Histórico detalhado do aluno, sorteios e código de tentativas | `StudentDetailReport` (`404` se aluno não existir) |
| `GET /api/units/{code}` | Taxa de acerto e métricas por questão da unidade | `UnitDetailReport` (`404` se unidade não existir) |
| `GET /api/export.csv?unit=...` | Download do arquivo de notas da unidade | Arquivo `text/csv` com header `Content-Disposition: attachment; filename="notas-<unit>.csv"` |

---

## 3. Desenvolvimento e Execução

### Em Desenvolvimento:
1. Inicie a API FastAPI:
   ```bash
   uv run unicode-web --port 8000
   ```
2. Inicie o servidor Vite no diretório `web/`:
   ```bash
   cd web
   npm install
   npm run dev
   ```
   O Vite roda em `http://localhost:5173` e faz proxy automático de `/api` para `http://127.0.0.1:8000`.

### Em Produção (Single-Process):
1. Compile os assets estáticos do React:
   ```bash
   cd web
   npm run build
   ```
   Isso gerará os arquivos estáticos em `web/dist/`.
2. O próprio servidor FastAPI servirá a SPA e os endpoints na mesma porta (configurado por padrão via `UNICODE_WEB_DIST_DIR=web/dist`):
   ```bash
   uv run unicode-web --host 0.0.0.0 --port 8000
   ```

