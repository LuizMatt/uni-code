# Guia de Operações na VPS: Gestão de Alunos no Painel Web

Este guia descreve o passo a passo para aplicar as alterações de gestão de alunos (Adicionar, Editar, Excluir individual, Apagar Turma e Importar CSV) na VPS de produção (Coolify / Docker Compose).

---

## 1. Conectar à VPS e Atualizar a Branch

Acesse a VPS via SSH e navegue até a pasta do projeto:

```bash
cd /srv/unicode  # ou o caminho onde o repositório está clonado na VPS
git fetch origin
git checkout feat/student-management-web
# Ou, após fazer o merge na main:
# git checkout main && git pull origin main
```

---

## 2. Aplicar a Migração do Banco de Dados (Alembic)

A nova migração (`0003_panel_write_permissions.py`) concede os privilégios necessários de escrita ao papel `unicode_panel` (`INSERT, UPDATE, DELETE` nas tabelas `students`, `assignments`, `attempts`, `sessions`, além de `INSERT` no `audit_log`).

### Opção A: Executar via Docker Compose (Recomendado na VPS)

Se você utiliza o `docker-compose.prod.yml`:

```bash
docker compose -f docker-compose.prod.yml run --rm web alembic upgrade head
```

### Opção B: Executar no Host da VPS (com `uv`)

Caso você execute o ambiente Python diretamente no host com as variáveis de ambiente de produção configuradas:

```bash
UNICODE_OWNER_DATABASE_URL="postgresql://unicode_owner:SUA_SENHA_OWNER@127.0.0.1:5432/unicode" \
uv run alembic upgrade head
```

> [!TIP]
> Para confirmar que a migração foi aplicada com sucesso:
> ```bash
> docker compose -f docker-compose.prod.yml run --rm web alembic current
> ```
> O resultado deve exibir a revisão `0003` como `(head)`.

---

## 3. Reconstruir e Reiniciar o Container Web

Como o frontend React em `web/` foi atualizado (novos modais, botões de ação e endpoints integrados), o container precisa ser recompilado para gerar o novo bundle em `web/dist`:

```bash
# 1. Reconstruir a imagem Docker do web (compilação Node/Vite + empacotamento FastAPI)
docker compose -f docker-compose.prod.yml build web

# 2. Reiniciar o serviço web em background sem derrubar o PostgreSQL
docker compose -f docker-compose.prod.yml up -d web
```

---

## 4. Verificação de Funcionamento

1. Verifique os logs do container web:
   ```bash
   docker compose -f docker-compose.prod.yml logs -f web --tail 50
   ```
2. Verifique o status dos serviços:
   ```bash
   docker compose -f docker-compose.prod.yml ps
   ```
3. Abra o navegador no endereço do painel web:
   - Faça login com o email e senha do professor.
   - Acesse a página **Alunos**.
   - Teste:
     - Botão **"+ Novo Aluno"** para cadastrar um aluno de teste.
     - Botão **"Editar"** para alterar nome ou turma do aluno.
     - Botão **"Importar CSV"** enviando uma planilha de alunos.
     - Botão **"Excluir"** no aluno de teste criado.
     - Filtro por turma e botão **"Apagar Turma"** se desejar limpar uma turma de testes.
