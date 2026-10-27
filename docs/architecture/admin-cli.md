# CLI Administrativa (`unicode-admin`)

Guia de uso e especificação técnica dos comandos administrativos do UniCode.

## Comandos

### `unicode-admin import-alunos <arquivo.csv>`

Importa ou atualiza alunos a partir de um arquivo CSV.

- **Codificação:** UTF-8 (com ou sem BOM).
- **Delimitadores aceitos:** vírgula (`,`) ou ponto e vírgula (`;`), detectados automaticamente a partir do cabeçalho.
- **Cabeçalho:** tolerante a maiúsculas, minúsculas e acentuação (`Matrícula`, `E-mail`, etc.).
- **Colunas obrigatórias:** `matricula`, `email`.
- **Colunas opcionais:** `nome`, `turma`.
- **Colunas adicionais:** são ignoradas.
- **Comportamento de Upsert:**
  - Chave primária é a matrícula (preservando zeros à esquerda).
  - Se a matrícula já existe, atualiza email, nome e turma. Valores em branco no CSV preservam o valor já cadastrado no banco (não apagam dados existentes).
  - Se o email pertencer a outra matrícula, a linha é rejeitada com mensagem de erro sem interromper o lote.
- **Deduplicação no próprio arquivo:**
  - Linhas idênticas são importadas uma única vez e geram aviso (warning).
  - Conflitos (mesma matrícula com dados diferentes ou mesmo email para matrículas distintas no arquivo) rejeitam todas as linhas envolvidas.
- **Auditoria:** registra o evento em `audit_log` com quantidade de criados, atualizados, inalterados e rejeitados.
- **Códigos de Saída:**
  - `0`: Todos os alunos válidos foram processados sem erros.
  - `1`: Importação parcial (algumas linhas continham erros e foram rejeitadas).
  - `2`: Erro fatal (arquivo não encontrado, erro de codificação, CSV malformado ou banco inacessível).

### `unicode-admin list-alunos [--turma <turma>]`

Lista os alunos cadastrados no banco em ordem crescente de matrícula, com suporte a filtro opcional por turma.

```
MATRÍCULA  EMAIL               NOME            TURMA
00123      joao@uni.edu        João Silva      T01
00124      maria@uni.edu       Maria Souza     T01

2 aluno(s)
```

## Permissões de Banco de Dados

A CLI conecta-se usando o papel `unicode_daemon` (`UNICODE_DATABASE_URL`), que possui privilégios de `SELECT`, `INSERT` e `UPDATE` na tabela `students` e `INSERT` em `audit_log`.
