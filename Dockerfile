FROM python:3.12-slim

# uv installe exactement les versions de uv.lock (≈ dotnet restore --locked-mode)
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY agentinsurflow ./agentinsurflow
RUN uv sync --locked --no-dev

# Version servie par /health : le SHA du commit, gravé au build
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION PATH="/app/.venv/bin:$PATH"

USER nobody
EXPOSE 8000
CMD ["uvicorn", "agentinsurflow.api:app", "--host", "0.0.0.0", "--port", "8000"]
