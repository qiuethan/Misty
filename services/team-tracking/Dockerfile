FROM python:3.11-slim

# Pull the uv binary from its official image (no pip bootstrap needed).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy the whole project (contracts/, src/, migrations/, alembic.ini, pyproject.toml, uv.lock).
COPY . .

# Install locked, production-only dependencies into /app/.venv.
RUN uv sync --frozen --no-dev

# Put the project venv on PATH so `uvicorn` resolves directly.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Migrations (`alembic upgrade head`) run as a separate deploy step, NOT here.
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
