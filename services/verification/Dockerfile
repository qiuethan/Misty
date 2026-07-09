FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Workspace root manifest + lockfile, the shared package(s), and this service.
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/verification/ ./services/verification/

# Sync only this member (+ workspace deps) into the root .venv.
RUN uv sync --frozen --no-dev --package verification

ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app/services/verification

EXPOSE 8003

# Migrations run as a separate deploy step, NOT here.
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8003"]
