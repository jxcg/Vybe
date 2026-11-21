FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache
COPY app/ ./app/
COPY --from=frontend /build/dist ./web/dist

CMD ["sh", "-c", "exec .venv/bin/uvicorn app.main:app --workers 1 --host 0.0.0.0 --port ${PORT:-8000}"]
