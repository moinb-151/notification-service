FROM python:3.13-slim-trixie AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev


FROM python:3.13-slim-trixie AS runtime

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

COPY . .

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["/app/entrypoint.sh"]