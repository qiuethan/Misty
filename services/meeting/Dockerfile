FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Audio decode/mix (src/audio) shells out to the ffmpeg binary -- install it
# before the dependency-install layer so it's cached independently of the
# Python deps below.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# Workspace root manifest + lockfile, the shared package(s), and this service.
COPY pyproject.toml uv.lock ./
COPY packages/ ./packages/
COPY services/meeting/ ./services/meeting/

# Sync only this member (+ workspace deps) into the root .venv.
RUN uv sync --frozen --no-dev --package meeting

ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app/services/meeting

# Run unprivileged (Trivy DS-0002).
RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8003

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8003"]
