# Contexte = racine du monorepo (uv.lock de l'espace de travail) : docker build -f agentic-cluster/Dockerfile .
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
RUN uv sync --locked --no-dev --package agentinsurflow-cluster --no-install-workspace
# le paquet porte les prompts versionnés (infrastructure/llm/prompts) ; garde_fous.env : seuils et sujets
COPY agentic-cluster/agentinsurflow_cluster agentic-cluster/agentinsurflow_cluster
COPY agentic-cluster/garde_fous.env agentic-cluster/
RUN uv sync --locked --no-dev --package agentinsurflow-cluster

# Modèles LLM Guard / Hugging Face téléchargés au build (≈ 2,5 Go) : le démarrage n'a plus besoin
# du réseau, HF_HUB_OFFLINE l'interdit. Lisibles par `nobody`.
ENV HF_HOME=/opt/hf PATH="/app/.venv/bin:$PATH"
WORKDIR /app/agentic-cluster
RUN python -c "from agentinsurflow_cluster.infrastructure.garde_fous.llm_guard import ScannersLlmGuard; ScannersLlmGuard()" \
    && chmod -R a+rX /opt/hf
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

# Versions servies par /health, gravées au build : SHA du commit
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION OTEL_SERVICE_NAME=agentic-cluster

USER nobody
# 8004 : gateway 8000, rag 8001, underwriting-admin 8002, serveur-mcp 8003
EXPOSE 8004
CMD ["uvicorn", "agentinsurflow_cluster.api:app", "--host", "0.0.0.0", "--port", "8004", "--no-access-log"]
