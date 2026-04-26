# ── builder: instala deps de producción con lockfile ─────────────────────────
FROM python:3.12-slim-trixie AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install uv --no-cache-dir

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ── runtime: imagen mínima, sin build deps, usuario no-root ──────────────────
FROM python:3.12-slim-trixie AS runtime

ARG BUILD_VERSION=dev
ARG BUILD_REVISION=unknown
ARG BUILD_CREATED=unknown

LABEL org.opencontainers.image.source="https://github.com/petrocast/petrocast" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.created="${BUILD_CREATED}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade "pip>=26.0" && \
    groupadd -g 10001 app && \
    useradd -r -u 10001 -g app app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --chown=app:app src/ ./src/

USER 10001

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
