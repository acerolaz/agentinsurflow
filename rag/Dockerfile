# Contexte = racine du monorepo (uv.lock de l'espace de travail) : docker build -f rag/Dockerfile .
FROM python:3.12-slim

# uv installe exactement les versions de uv.lock (≈ dotnet restore --locked-mode)
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY rag/pyproject.toml rag/
COPY serveur-mcp/pyproject.toml serveur-mcp/
COPY fonction-calcul/pyproject.toml fonction-calcul/
COPY agentic-cluster/pyproject.toml agentic-cluster/
RUN uv sync --locked --no-dev --package agentinsurflow-rag --no-install-workspace
COPY rag/agentinsurflow_rag rag/agentinsurflow_rag
COPY rag/llm.env rag/alembic.ini rag/demarrer.sh rag/
COPY rag/migrations rag/migrations
RUN uv sync --locked --no-dev --package agentinsurflow-rag

# Versions servies par /health, gravées au build : SHA du commit, release vX.Y.Z, manifeste
ARG APP_VERSION=dev APP_RELEASE=dev APP_MANIFESTE=dev
ENV APP_VERSION=$APP_VERSION APP_RELEASE=$APP_RELEASE APP_MANIFESTE=$APP_MANIFESTE \
    PATH="/app/.venv/bin:$PATH"

# llm.env est lu dans le répertoire courant
WORKDIR /app/rag
USER nobody
# 8001 : la gateway écoute sur 8000 dans la même Container App (G5)
EXPOSE 8001
# migrations (compte migrateur) puis uvicorn : voir demarrer.sh
CMD ["sh", "demarrer.sh"]
