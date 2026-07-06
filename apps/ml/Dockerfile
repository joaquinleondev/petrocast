# ── builder: instala deps de producción con lockfile ─────────────────────────
# Build context: apps/ (igual que api/data) → docker build -f ml/Dockerfile .
FROM python:3.12-slim-trixie AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /app/apps/ml

COPY ml/pyproject.toml ml/uv.lock ml/README.md ./
COPY ml/src ./src
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
    PATH="/app/apps/ml/.venv/bin:$PATH"

# libgomp1: OpenMP runtime that lightgbm loads via ctypes at import time. This
# image trains and loads LightGBM, so the slim base — which omits it — would
# otherwise crash on any command with "libgomp.so.1: cannot open".
RUN apt-get update && \
    echo "apt cache buster: ${APT_CACHE_BUSTER}" >/dev/null && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends libgomp1 && \
    rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade "pip>=26.0" && \
    groupadd -g 10001 app && \
    useradd -r -u 10001 -g app app

WORKDIR /app/apps/ml

COPY --from=builder /app/apps/ml/.venv /app/apps/ml/.venv
COPY --from=builder --chown=app:app /app/apps/ml/src /app/apps/ml/src
# Contract-A offline fixtures (F3-10): let the image run the training smoke
# without a warehouse or MLflow server (F3-23).
COPY --chown=app:app ml/tests/fixtures ./tests/fixtures

USER 10001

# Default smoke: importing the package exercises the lightgbm/libgomp load.
# Offline training smoke inside the image:
#   docker run --rm petrocast-ml:dev python -m petrocast_ml.training \
#     --features-csv tests/fixtures/well_features.csv \
#     --production-csv tests/fixtures/production_monthly.csv \
#     --as-of 2026-01-01 --horizons 1,2,3 --output-dir /tmp/artifacts
CMD ["python", "-c", "import petrocast_ml"]
