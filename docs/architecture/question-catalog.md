# Catálogo de Questões e Sincronização

Especificação técnica e guia prático para criação, estruturação e sincronização de unidades e questões no UniCode.

---

## 1. Visão Geral e Arquitetura

O catálogo de questões do UniCode é armazenado de forma declarativa e versionada no sistema de arquivos (por padrão no diretório `questions/`), enquanto o estado transacional e de avaliação reside no banco de dados PostgreSQL.

O sistema divide o ciclo em duas etapas isoladas:
1. **Varredura e Validação em Memória (`scan_and_validate_questions_dir`):**
   Percorre o diretório no disco, valida a estrutura de diretórios, formatação de YAMLs, campos obrigatórios, datas e arquivos mínimos exigidos sem tocar no banco de dados.
2. **Sincronização Atômica com o Banco (`sync_questions`):**
   Executa o upsert de unidades e questões via transações controladas pelo chamador, preserva integridade histórica (desativação lógica via `active = FALSE` em vez de `DELETE`) e grava evento detalhado na tabela `audit_log`.

A interface principal do professor para sincronização é a CLI administrativa: `unicode-admin sync-questoes`.

---

## 2. Estrutura de Diretórios (`questions/`)

O diretório raiz do catálogo organiza-se hierarquicamente por **unidades** e, dentro de cada unidade, por **questões**:

```text
questions/
├── .gitkeep
└── <unit-code>/                     # Ex: unit-01
    ├── unit.yaml                    # Metadados e prazos da unidade
    └── <question-slug>/             # Ex: soma-dois-numeros
        ├── question.yaml            # Metadados da questão (título, timeout, etc.)
        ├── README.md                # Enunciado formatado em Markdown
        ├── template.py              # Código base inicial entregue ao aluno
        └── test_eval.py             # Testes de avaliação (Pytest) executados no container
```

### Regras de Nomenclatura e Pastas
- Diretórios que começam com ponto (`.`) são sumariamente ignorados pelo scanner.
- O nome da pasta da unidade **deve coincidir exatamente** com o campo `code` do arquivo `unit.yaml`.
- O nome da pasta da questão (`slug`) deve conter apenas **letras minúsculas, números e hifens** (expressão regular: `^[a-z0-9-]+$`).
- O `slug` de uma questão deve ser **globalmente único** em todo o catálogo (duas unidades não podem conter questões com o mesmo slug).

---

## 3. Como Criar uma Unidade (`unit.yaml`)

Cada unidade de ensino possui uma pasta própria na raiz de `questions/` (ex: `questions/unit-01/`). Dentro dela, o arquivo `unit.yaml` é obrigatório.

### Estrutura do `unit.yaml`

```yaml
code: unit-01
title: Unidade 1 - Introdução ao Python
opens_at: "2026-03-01T00:00:00Z"    # Opcional (ISO 8601 UTC)
closes_at: "2026-04-01T23:59:59Z"   # Opcional (ISO 8601 UTC)
```

### Campos

| Campo | Tipo | Obrigatório? | Descrição e Validação |
|---|---|---|---|
| `code` | `string` | **Sim** | Identificador único da unidade. Deve corresponder exatamente ao nome do diretório da unidade. |
| `title` | `string` | **Sim** | Nome legível e descritivo da unidade (não pode ser vazio). |
| `opens_at` | `ISO 8601` | Não | Data/hora de abertura da unidade para os alunos. |
| `closes_at` | `ISO 8601` | Não | Data/hora de fechamento da unidade. Se ambos forem definidos, `closes_at` **deve ser posterior** a `opens_at`. |

---

## 4. Como Criar uma Questão

Cada questão deve ser criada em uma subpasta dentro de sua respectiva unidade (ex: `questions/unit-01/soma-dois-numeros/`).

Uma questão é composta **obrigatoriamente** por 4 arquivos:

### 4.1. `question.yaml` (Metadados da Questão)

```yaml
title: Soma de Dois Números
active: true
timeout_seconds: 3
```

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `title` | `string` | *(obrigatório)* | Título descritivo da questão exibido na interface e listagens. |
| `active` | `boolean` | `true` | Se `true`, a questão está ativa para sorteio. Se `false`, permanece inativa. |
| `timeout_seconds` | `integer` | `3` | Tempo limite máximo (em segundos) concedido para a execução dos testes de avaliação no container. |

### 4.2. `README.md` (Enunciado do Problema)

Documento em Markdown com o enunciado claro, especificação da assinatura da função ou entrada/saída esperada e exemplos:

````markdown
# Soma de Dois Números

Escreva uma função `soma(a: int, b: int) -> int` que recebe dois números inteiros e retorna a soma deles.

## Exemplo

```python
assert soma(2, 3) == 5
assert soma(-1, 1) == 0
```
````

### 4.3. `template.py` (Esqueleto Inicial)

Arquivo Python fornecido ao aluno ao iniciar a questão. Contém a assinatura da função e comentários de apoio:

```python
def soma(a: int, b: int) -> int:
    pass
```

### 4.4. `test_eval.py` (Suíte de Avaliação)

Arquivo Pytest executado pelo avaliador/runner seguro para testar a solução do aluno. Ele importa a função a partir de `solution` (o código submetido pelo aluno):

```python
from solution import soma


def test_soma_positivos() -> None:
    assert soma(2, 3) == 5


def test_soma_com_negativos() -> None:
    assert soma(-1, 1) == 0
    assert soma(-5, -5) == -10


def test_soma_com_zero() -> None:
    assert soma(0, 0) == 0
    assert soma(10, 0) == 10
```

---

## 5. Ciclo de Sincronização e Regras de Negócio

Quando o comando de sincronização é executado:

1. **Validação Estrita:**
   Se qualquer unidade ou questão violar regras de sintaxe, campos ausentes, datas inconsistentes ou arquivos faltantes, **a sincronização é abortada antes de qualquer alteração no banco**.

2. **Upsert Atômico de Unidades:**
   - Se a unidade (por `code`) não existir na tabela `units`, é inserida com `id` gerado via `RETURNING id`.
   - Se já existir, campos divergentes (`title`, `opens_at`, `closes_at`) são atualizados via `UPDATE`.

3. **Upsert Atômico de Questões:**
   - Se a questão (por `slug`) não existir na tabela `questions`, é inserida vinculada à sua unidade (`unit_id`).
   - Se já existir, atualiza `unit_id`, `title` e `active`.

4. **Desativação Lógica (Soft-Disable):**
   - **Nunca é feito `DELETE` físico** de questões no banco de dados.
   - Questões que existiam no banco para uma unidade mas foram removidas ou renomeadas nas pastas do disco têm seu status atualizado para `active = FALSE`.
   - **Por que essa regra é crítica:** Alunos já podem ter recebido sorteios (`assignments`) e registrado tentativas (`attempts`) com notas calculadas vinculadas à questão. O `active = FALSE` preserva integralmente a rastreabilidade histórica e o cálculo de notas na view `grades_by_unit`.

5. **Auditoria (`audit_log`):**
   - Toda execução bem-sucedida de sincronização insere um registro na tabela `audit_log`:
     - `actor`: usuário executor (padrão `'admin'`).
     - `action`: `'sync_questions'`.
     - `details`: payload JSON com contadores:
       ```json
       {
         "units_created": 1,
         "units_updated": 0,
         "questions_created": 2,
         "questions_updated": 0,
         "questions_deactivated": 0
       }
       ```

---

## 6. Uso da CLI (`unicode-admin sync-questoes`)

### Sintaxe

```bash
unicode-admin sync-questoes [--dir <caminho>]
```

- `--dir`, `-d` *(opcional)*: Caminho do diretório raiz de questões. Se omitido, utiliza a configuração padrão do ambiente `UNICODE_QUESTIONS_DIR` (padrão: `./questions`).

### Exemplo de Sucesso

```text
$ unicode-admin sync-questoes
Sincronização de questions
  unidades criadas:     1
  unidades atualizadas: 0
  questões criadas:     2
  questões atualizadas: 0
  questões desativadas: 0
```

### Exemplo com Erros de Validação

```text
$ unicode-admin sync-questoes --dir /tmp/questoes-com-erro
Sincronização de /tmp/questoes-com-erro
  unidades criadas:     0
  unidades atualizadas: 0
  questões criadas:     0
  questões atualizadas: 0
  questões desativadas: 0

Erros (sincronização não efetuada):
  /tmp/questoes-com-erro/unit-01/incompleta: arquivos obrigatórios ausentes: README.md, template.py
```

### Códigos de Saída (Exit Codes)

| Código | Significado |
|---|---|
| `0` | Sucesso total: catálogo validado e sincronizado com o banco. |
| `1` | Erros de validação no catálogo: nenhuma alteração foi persistida no banco. |
| `2` | Erro fatal: diretório de questões não encontrado ou falha de conexão com o PostgreSQL. |
