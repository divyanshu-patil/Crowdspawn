# Crowdspawn API. Build from apps/api: docker build -t crowdspawn-api .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.17 /uv /uvx /bin/
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 APP_ENV=production PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
# Keys come from the host's environment (never baked into the image). SQLite lives in /app/data.
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync uvicorn crowdspawn_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
