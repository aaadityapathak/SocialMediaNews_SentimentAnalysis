FROM python:3.13-slim

ENV SERVER_PORT=8004 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

WORKDIR /app
RUN groupadd -g 1444 appusers \
    && useradd -m -u 1444 -g appusers appuser \
    && chown -R appuser:appusers /app \
    && chmod -R 755 /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
USER appuser

COPY --chown=appuser:appusers pyproject.toml uv.lock ./
COPY --chown=appuser:appusers backend/ml-server/pyproject.toml ./backend/ml-server/

RUN uv sync --package ml-server --no-dev --no-install-project --frozen

COPY --chown=appuser:appusers backend/ml-server/src ./backend/ml-server/src
COPY --chown=appuser:appusers backend/ml-server/hf-models ./backend/ml-server/hf-models

EXPOSE 8004

WORKDIR /app/backend/ml-server/src

CMD ["uv", "run", "--no-sync", "main.py"]
