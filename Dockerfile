# Multi-stage build para o UniCode (FastAPI + React 19 SPA)

# --- Estágio 1: Build do Frontend (React + Vite + Tailwind CSS) ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app/web

# Cache das dependências npm
COPY web/package*.json ./
RUN npm ci

# Compilação da aplicação SPA
COPY web/ ./
RUN npm run build

# --- Estágio 2: Execução do Backend FastAPI + Servidor de SPA ---
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UNICODE_WEB_DIST_DIR=/app/web/dist

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

# Instala a aplicação unicode e o uvicorn
RUN pip install --no-cache-dir .

# Copia os assets estáticos gerados no Estágio 1
COPY --from=frontend-builder /app/web/dist /app/web/dist

EXPOSE 8000

CMD ["unicode-web", "--host", "0.0.0.0", "--port", "8000"]

