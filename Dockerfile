FROM python:3.12-slim

# uv installe exactement les versions de uv.lock (≈ dotnet restore --locked-mode)
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY agentinsurflow ./agentinsurflow
COPY llm.env ./
RUN uv sync --locked --no-dev

# Versions servies par /health, gravées au build : SHA du commit, release vX.Y.Z, manifeste
ARG APP_VERSION=dev APP_RELEASE=dev APP_MANIFESTE=dev
ENV APP_VERSION=$APP_VERSION APP_RELEASE=$APP_RELEASE APP_MANIFESTE=$APP_MANIFESTE \
    PATH="/app/.venv/bin:$PATH"

USER nobody
EXPOSE 8000
CMD ["uvicorn", "agentinsurflow.api:app", "--host", "0.0.0.0", "--port", "8000"]
