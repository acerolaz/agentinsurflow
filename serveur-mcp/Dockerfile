# Contexte = racine du monorepo (uv.lock de l'espace de travail) : docker build -f serveur-mcp/Dockerfile .
FROM python:3.12-slim

# uv installe exactement les versions de uv.lock (≈ dotnet restore --locked-mode)
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY rag/pyproject.toml rag/
COPY serveur-mcp/pyproject.toml serveur-mcp/
COPY fonction-calcul/pyproject.toml fonction-calcul/
RUN uv sync --locked --no-dev --package agentinsurflow-mcp --no-install-workspace
COPY serveur-mcp/agentinsurflow_mcp serveur-mcp/agentinsurflow_mcp
RUN uv sync --locked --no-dev --package agentinsurflow-mcp

# Versions servies par /health, gravées au build : SHA du commit, release vX.Y.Z
ARG APP_VERSION=dev APP_RELEASE=dev
ENV APP_VERSION=$APP_VERSION APP_RELEASE=$APP_RELEASE \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app/serveur-mcp
USER nobody
# 8003 : la gateway écoute sur 8000, rag 8001, underwriting-admin 8002 (même Container App)
EXPOSE 8003
CMD ["uvicorn", "agentinsurflow_mcp.api.app:app", "--host", "0.0.0.0", "--port", "8003", "--no-access-log"]
