# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm@sha256:d193c6f51a7dbd10395d6328de3a7edb0516fb0608ca138036576f574c3e07d2 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5.11@sha256:0ac957607303916420297a4c9c213bb33fbd3c888f9cd7f4f7273596ebf42b85 /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock* README.md ./
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# -----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm@sha256:d193c6f51a7dbd10395d6328de3a7edb0516fb0608ca138036576f574c3e07d2 AS runtime

LABEL io.modelcontextprotocol.server.name="io.github.lucasmaffei/mailgrant" \
      org.opencontainers.image.source="https://github.com/lucasmaffei/mailgrant" \
      org.opencontainers.image.description="One email gateway for many AI agents, each with its own mailboxes and scopes" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    TZ=UTC \
    LOG_LEVEL=INFO \
    WORKERS=2 \
    MAILGRANT_CONFIG=/etc/mailgrant/config.yaml

# /data only holds the web app's SQLite (passkeys, push devices, history);
# an MCP-only instance never writes to it.
RUN useradd --create-home --shell /bin/bash mailgrant \
    && mkdir -p /etc/mailgrant /data \
    && chown mailgrant:mailgrant /etc/mailgrant /data

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=mailgrant:mailgrant src ./src
COPY --chown=mailgrant:mailgrant pyproject.toml README.md ./

USER mailgrant

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)" || exit 1

CMD ["sh", "-c", "uvicorn --factory mailgrant.server:create_app --host 0.0.0.0 --port 8000 --workers ${WORKERS}"]
