# Contexte = racine du monorepo (uv.lock de l'espace de travail) : docker build -f rag/Dockerfile .
FROM python:3.12-slim

# uv installe exactement les versions de uv.lock (≈ dotnet restore --locked-mode)
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY rag/pyproject.toml rag/
RUN uv sync --locked --no-dev --package agentinsurflow-rag --no-install-workspace
COPY rag/agentinsurflow_rag rag/agentinsurflow_rag
COPY rag/llm.env rag/
RUN uv sync --locked --no-dev --package agentinsurflow-rag

# Versions servies par /health, gravées au build : SHA du commit, release vX.Y.Z, manifeste
ARG APP_VERSION=dev APP_RELEASE=dev APP_MANIFESTE=dev
ENV APP_VERSION=$APP_VERSION APP_RELEASE=$APP_RELEASE APP_MANIFESTE=$APP_MANIFESTE \
    PATH="/app/.venv/bin:$PATH"

# llm.env est lu dans le répertoire courant
WORKDIR /app/rag
USER nobody
EXPOSE 8000
# pas de journal d'accès : il écrirait la query string (/api/extraits?question=…, RGPD)
CMD ["uvicorn", "agentinsurflow_rag.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
