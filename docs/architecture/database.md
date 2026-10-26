# Banco de dados

Como o banco do UniCode funciona hoje e como alterá-lo com segurança.

## Visão geral

| Peça | Onde |
|---|---|
| Postgres 16 (dev) | `docker-compose.yml` |
| Papéis e bancos | `docker/postgres/init/01-roles-and-databases.sql` |
| Migrations (SQL puro) | `migrations/versions/` |
| Acesso em Python | `src/unicode/db.py` |
| Configuração | `src/unicode/config.py` (`UNICODE_*`) |

## Rodando localmente

```powershell
docker compose up -d --wait          # sobe o Postgres
uv run alembic upgrade head          # aplica as migrations no banco "unicode"
uv run pytest                        # testes (usam o banco "unicode_test")
docker compose down -v               # derruba e APAGA os dados (re-roda o init)
```

O script de init só roda com o volume vazio. Se você mudar papéis ou senhas, rode `docker compose down -v`.

## Papéis

| Papel | Uso | Privilégios |
|---|---|---|
| `unicode_owner` | Dono dos bancos; roda as migrations | Tudo (dono) |
| `unicode_daemon` | `unicode-daemon` e `unicode-admin` | SELECT/INSERT/UPDATE no domínio; DELETE só em `sessions`; `audit_log` só INSERT/SELECT |
| `unicode_panel` | Painel web | Somente SELECT; sem acesso a `sessions` |

- Os papéis (com senha) são criados **fora** das migrations, pelo script de init. As migrations só fazem GRANT/REVOKE e falham se os papéis não existirem.
- O aluno não tem papel nenhum.
- **Produção:** rode o script de init manualmente como superusuário, com as senhas em variáveis de ambiente (instruções no cabeçalho do arquivo). Depois rode `alembic upgrade head` com `UNICODE_MIGRATIONS_DATABASE_URL` apontando para o `unicode_owner`.

## Schema

Nomes em inglês. A tabela a seguir mapeia os termos do CLAUDE.md:

| Conceito (CLAUDE.md) | Tabela | Observações |
|---|---|---|
| aluno | `students` | PK `registration TEXT` (preserva zeros à esquerda, sem espaços nas pontas); `email CITEXT UNIQUE` |
| unidade | `units` | `opens_at`/`closes_at` reservados para o futuro |
| questão | `questions` | `slug UNIQUE`; `UNIQUE (id, unit_id)` para a FK composta |
| sorteio | `assignments` | `state`: `pending`/`passed`/`exhausted`/`replaced`; `points` 0 ou 0.5 |
| tentativa | `attempts` | `number` de 1 a 3, único por assignment; `status`: `running`/`passed`/`failed`/`error` |
| sessão | `sessions` | `token_hash` = sha256 do token (32 bytes); o token puro nunca é gravado |
| auditoria | `audit_log` | append-only para o daemon |
| nota | view `grades_by_unit` | soma `points` por aluno/unidade, ignorando `replaced` |

### Invariantes garantidas pelo banco

| Invariante | Mecanismo |
|---|---|
| Assignment aponta para uma questão da mesma unidade | FK composta `(question_id, unit_id) → questions(id, unit_id)` |
| `points = 0.5` ⇔ `state = 'passed'` | `ck_assignments_points_match_state` (um reset de questão aprovada zera os pontos; o histórico fica em `attempts`) |
| No máximo um assignment não substituído por (aluno, questão) | índice único parcial `uq_assignments_active` |
| No máximo 3 tentativas, numeradas e sem repetição | `CHECK (number BETWEEN 1 AND 3)` + `UNIQUE (assignment_id, number)` |
| `tests_passed ≤ tests_total` | CHECK |
| Histórico nunca é apagado | FKs `RESTRICT` + o daemon não tem DELETE |
| Ids não são forjados | `GENERATED ALWAYS AS IDENTITY` |

### Invariantes que ficam a cargo dos services (não do banco)

- Exatamente 2 assignments ativos por (aluno, unidade).
- A sequência das tentativas (não pular números) e a regra "não submeter após `passed`/`exhausted`".
- Esses pontos são cobertos por testes dos services (Etapas 4 e 6).

## Acesso em Python (`unicode.db`)

```python
from unicode.db import transaction

with transaction() as conn:                 # pega a conexão do pool global
    conn.execute("INSERT INTO audit_log (actor, action) VALUES (%s, %s)", ("admin", "x"))
    row = conn.execute("SELECT count(*) AS n FROM students").fetchone()  # {'n': ...}
```

- `transaction(pool=None)`: COMMIT ao sair normalmente; ROLLBACK e re-raise em exceção.
- As linhas vêm como `dict` (`DictConnection`).
- **Regra:** services recebem `conn: DictConnection` e **não** abrem transação. Quem chama (daemon/CLI) decide os limites. Exemplo: a submissão usa duas transações curtas, com a sandbox no meio.
- `get_pool()` cria o pool na primeira chamada (o daemon deve chamá-la no startup); `close_pool()` no shutdown.
- Configuração: `UNICODE_DATABASE_URL` (papel daemon), `UNICODE_DB_POOL_MIN_SIZE`, `UNICODE_DB_POOL_MAX_SIZE`.

## Migrations

- Alembic, mas **sem ORM**: cada revisão tem listas `UPGRADE`/`DOWNGRADE` de statements SQL executados com `op.execute`.
- Um statement por item. **Não use `:` no SQL** (o SQLAlchemy interpreta `:nome` como parâmetro); prefira `CAST(x AS tipo)` a `x::tipo`.
- Ids de revisão sequenciais: `0001`, `0002`, ... (arquivo `NNNN_descricao.py`).
- A URL vem de `UNICODE_MIGRATIONS_DATABASE_URL` (papel owner).

### Como alterar o schema (checklist)

1. Crie `migrations/versions/NNNN_<descricao>.py` com `uv run alembic revision -m "<descricao>" --rev-id NNNN`.
2. Escreva `UPGRADE` **e** `DOWNGRADE` (o downgrade precisa desfazer exatamente o upgrade).
3. **Tabela ou view nova?** Adicione na mesma migration os GRANTs para `unicode_daemon` e, se fizer sentido, `unicode_panel`. Não há default privileges: sem GRANT, a aplicação recebe `permission denied`.
4. Atualize `tests/test_migrations.py` (`EXPECTED_TABLES`) e adicione testes para cada constraint nova em `tests/test_schema.py` ou `tests/test_grants.py`.
5. Rode `uv run pytest` (o round-trip downgrade/upgrade é testado) e `uv run alembic upgrade head`.
6. Atualize este documento.

> Nunca edite uma migration que já foi aplicada em produção; crie uma nova.

## Testes

- Banco `unicode_test`, recriado do zero (`downgrade base` + `upgrade head`) uma vez por sessão do pytest.
- Fixtures `owner_conn`, `daemon_conn`, `panel_conn`: cada teste roda numa transação que sofre rollback no final.
- Para testar violações sem invalidar a transação do teste, use um `with conn.transaction():` aninhado (SAVEPOINT).
- Os testes marcados com `db` são pulados se o Postgres estiver fora do ar. Rode só os unitários com `uv run pytest -m "not db"`.
- URLs sobrescrevíveis: `UNICODE_TEST_OWNER_URL`, `UNICODE_TEST_DAEMON_URL`, `UNICODE_TEST_PANEL_URL`.
