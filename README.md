# UniCode 🎓💻

Ambiente de questões de programação no estilo LeetCode para ensino prático e avaliações acadêmicas, com execução segura em sandbox, acesso por SSH para alunos e painel web gerencial para professores.

---

## 📌 Sobre o Projeto

O **UniCode** foi desenvolvido para automatizar a aplicação e correção de avaliações práticas de programação em Python com rigor, segurança e isolamento completo:

- **Sorteio Idempotente:** Cada unidade possui um banco de questões (ex.: 5 questões). Cada aluno recebe 2 questões sorteadas de forma determinística e persistida no banco; reconectar ao sistema nunca altera as questões sorteadas.
- **Tentativas e Avaliação:** Cada questão permite até **3 tentativas de submissão**. A pontuação é **tudo-ou-nada** (passou em 100% dos testes ocultos = 0,5 pontos; caso contrário = 0 pontos).
- **Isolamento e Segurança Máxima:** 
  - O aluno acessa o ambiente via SSH restrito (`ForceCommand`), entrando em um container descartável sem acesso à rede, montando unicamente sua pasta de trabalho.
  - O código do aluno é executado contra testes ocultos dentro de uma **sandbox Docker efêmera** com limites estritos de CPU, memória, tempo e sem privilégios de root.
  - O aluno nunca tem acesso às credenciais do banco de dados nem aos arquivos de testes ocultos.
- **Painel do Professor:** Single Page Application (SPA) moderna em React 19 conectada a uma API FastAPI (somente leitura) para monitorar em tempo real notas, submissões, taxas de acerto e exportar relatórios em CSV.

---

## 🛠️ Stack Tecnológica

- **Linguagem Principal:** Python 3.12 (gerenciado via [uv](https://docs.astral.sh/uv/))
- **Banco de Dados:** PostgreSQL 16 (com extensão `citext`)
- **Acesso ao Banco e Migrações:** `psycopg 3` (pool nativo) e `Alembic`
- **CLIs:** `Typer` (`unicode` para alunos e `unicode-admin` para professores)
- **API Backend:** `FastAPI` + `Uvicorn`
- **Frontend SPA:** `React 19`, `TypeScript`, `Vite` e `Tailwind CSS`
- **Virtualização & Sandbox:** `Docker` e `Docker Compose`

---

## 📂 Estrutura do Repositório

```text
unicode/
├── docker/                 # Definições Docker (shell do aluno, sandbox e postgres)
├── docs/                   # Documentação detalhada de arquitetura e decisões
├── migrations/             # Migrações versionadas do banco com Alembic
├── questions/              # Catálogo de unidades e questões (enunciados, templates e testes ocultos)
├── src/unicode/            # Código-fonte principal em Python
│   ├── config.py           # Configurações globais e leitura do .env
│   ├── db.py               # Pool de conexões e helpers de transação
│   ├── cli_admin.py        # CLI administrativa (unicode-admin)
│   ├── cli_student.py      # CLI do aluno (unicode)
│   ├── cli_daemon.py       # Daemon de serviço (unicode-daemon)
│   ├── cli_web.py          # Entrypoint do servidor web do painel
│   ├── daemon/             # Servidor IPC (Unix Domain Socket / TCP)
│   ├── sandbox/            # Orquestrador de execução em container efêmero
│   ├── services/           # Regras de negócio (alunos, sorteio, submissão, notas)
│   └── web/                # API REST do painel do professor (FastAPI)
├── tests/                  # Testes automatizados (pytest)
├── web/                    # Frontend React 19 + TypeScript + Vite + Tailwind CSS
├── docker-compose.yml      # PostgreSQL de desenvolvimento
├── pyproject.toml          # Dependências do projeto Python
└── README.md
```

---

## 🚀 Como Inicializar o Projeto Localmente

### 1. Pré-requisitos

Certifique-se de ter instalado em sua máquina:
- [Docker](https://www.docker.com/) e Docker Desktop rodando.
- [uv](https://github.com/astral-sh/uv) (gerenciador de pacotes e ambientes virtuais Python).
- [Node.js](https://nodejs.org/) (versão 18+) e `npm`.

### 2. Configurar Variáveis de Ambiente

Copie o arquivo de exemplo para criar seu `.env`:

```bash
cp .env.example .env
```

*(No Windows PowerShell: `Copy-Item .env.example .env`)*

Certifique-se de que as portas e credenciais no `.env` correspondam ao seu ambiente local (por padrão, a porta do PostgreSQL é mapeada para `5433` para evitar conflitos com instâncias locais existentes).

### 3. Iniciar o Banco de Dados

Suba o container do PostgreSQL via Docker Compose:

```bash
docker compose up -d postgres
```

### 4. Executar as Migrações do Banco de Dados

Aplique as migrações com o Alembic para criar tabelas, views e papéis de acesso:

```bash
uv run alembic upgrade head
```

### 5. Popular Dados Iniciais e Usuários de Teste (Seed)

Para sincronizar o catálogo de questões e popular o banco com turmas, alunos e histórico de submissões simuladas (aprovados, reprovados e com tentativas esgotadas):

```bash
uv run python seed.py
```

*(Opcional: Para importar manualmente outra lista de alunos via CSV, você também pode usar `uv run unicode-admin import-alunos alunos_teste.csv`)*.

---

## 👥 Usuários e Credenciais de Teste

| Perfil | Identificador / E-mail | Senha / Acesso | Situação Inicial |
| :--- | :--- | :--- | :--- |
| **Professor / Admin** | `admin@unicode.local` | `change-me-in-prod` | Administrador geral; acesso total ao painel web, turmas, métricas e exportação de CSV |
| **Aluno** | `202601001` (Lucas Silva) | Sessão / SSH | TURMA-A · Unidade 1 iniciada · 1 questão aprovada (0,5 ponto) |
| **Aluna** | `202601002` (Beatriz Mendes) | Sessão / SSH | TURMA-A · Unidade 1 iniciada · 2 tentativas gastas com falhas (1 restante) |
| **Aluno** | `202601003` (Rodrigo Souza) | Sessão / SSH | TURMA-A · Unidade 1 iniciada · 3 tentativas esgotadas (0,0 pontos) |
| **Aluna** | `202601004` (Camila Rocha) | Sessão / SSH | TURMA-B · Cadastrada · Nenhuma avaliação iniciada |
| **Aluno** | `202601099` (Marcos Lima) | Bloqueado | TURMA-B · Matrícula trancada (conta inativa) |

---

## 🖥️ Executando o Painel do Professor (Web)

O painel administrativo pode ser executado em modo de desenvolvimento ou integrado (produção local).

### Modo de Desenvolvimento (Vite com Hot-Reload + API FastAPI)

1. **Terminal 1 — Iniciar a API Backend:**
   ```bash
   uv run unicode-web --port 8000
   ```

2. **Terminal 2 — Iniciar o Frontend Vite:**
   ```bash
   cd web
   npm install
   npm run dev
   ```
   Acesse no navegador: **[http://localhost:5173](http://localhost:5173)**

### Modo de Produção / Single-Process (FastAPI servindo a SPA)

1. Compile os assets do frontend:
   ```bash
   cd web
   npm install
   npm run build
   cd ..
   ```

2. Inicie o servidor unificado:
   ```bash
   uv run unicode-web --port 8000
   ```
   Acesse no navegador: **[http://localhost:8000](http://localhost:8000)**

#### 🔑 Credenciais Padrão de Acesso:
- **Email:** `admin@unicode.local`
- **Senha:** `change-me-in-prod` *(ou a senha definida na variável `UNICODE_ADMIN_PASSWORD` no `.env`)*

---

## 💻 Comandos das CLIs

### CLI do Aluno (`unicode`)
- `unicode status`: Exibe as questões sorteadas, notas e tentativas restantes.
- `unicode start <unidade>`: Sorteia as questões da unidade e provisiona a pasta de trabalho.
- `unicode test <questao>`: Executa testes públicos locais sem gastar tentativas.
- `unicode submit <questao>`: Envia a solução para a sandbox de avaliação (consome 1 tentativa).

### CLI Administrativa (`unicode-admin`)
- `unicode-admin sync-questoes`: Sincroniza unidades e questões de `questions/` com o banco.
- `unicode-admin list-alunos`: Lista todos os alunos cadastrados e suas turmas.
- `unicode-admin import-alunos <arquivo.csv>`: Importa ou atualiza alunos a partir de CSV.
- `unicode-admin reset <matricula> --unidade <codigo>`: Reseta os sorteios de um aluno e sorteia novas questões mantendo o histórico.

---

## 🧪 Testes Automatizados

Para rodar a suíte completa de testes automatizados com o pytest:

```bash
uv run pytest
```

