# ── builder: instala deps de producción con lockfile ─────────────────────────
FROM python:3.12-slim-trixie AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install uv --no-cache-dir

WORKDIR /app/apps/api

COPY api/pyproject.toml api/uv.lock ./
COPY ml/pyproject.toml ml/README.md /app/apps/ml/
COPY ml/src /app/apps/ml/src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# ── runtime: imagen mínima, sin build deps, usuario no-root ──────────────────
FROM python:3.12-slim-trixie AS runtime

ARG APT_CACHE_BUSTER=local
ARG BUILD_VERSION=dev
ARG BUILD_REVISION=unknown
ARG BUILD_CREATED=unknown

LABEL org.opencontainers.image.source="https://github.com/petrocast/petrocast" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.revision="${BUILD_REVISION}" \
      org.opencontainers.image.created="${BUILD_CREATED}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/apps/api/.venv/bin:$PATH"

# libgomp1: OpenMP runtime that lightgbm loads via ctypes at import time. The
# API imports the ML stack (F3-18 champion serving) so the slim base — which
# omits it — would otherwise crash on startup with "libgomp.so.1: cannot open".
RUN apt-get update && \
    echo "apt cache buster: ${APT_CACHE_BUSTER}" >/dev/null && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade "pip>=26.0" && \
    groupadd -g 10001 app && \
    useradd -r -u 10001 -g app app

WORKDIR /app/apps/api

COPY --from=builder /app/apps/api/.venv /app/apps/api/.venv
COPY --from=builder --chown=app:app /app/apps/ml/src /app/apps/ml/src
COPY --chown=app:app api/src/ ./src/

USER 10001

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
