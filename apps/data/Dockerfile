FROM python:3.12-slim-trixie AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/apps/data

RUN pip install --no-cache-dir uv

COPY data/pyproject.toml data/uv.lock data/README.md ./
COPY data/src ./src
COPY data/dbt ./dbt
COPY ml/pyproject.toml ml/README.md /app/apps/ml/
COPY ml/src /app/apps/ml/src

RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
RUN DBT_PROFILES_DIR=/app/apps/data/dbt /app/apps/data/.venv/bin/dbt deps --project-dir /app/apps/data/dbt --profiles-dir /app/apps/data/dbt
RUN DBT_PROFILES_DIR=/app/apps/data/dbt /app/apps/data/.venv/bin/dbt parse --project-dir /app/apps/data/dbt --profiles-dir /app/apps/data/dbt

FROM python:3.12-slim-trixie AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/apps/data/.venv/bin:${PATH}" \
    PYTHONPATH="/app/apps/data/src" \
    DAGSTER_HOME="/opt/dagster/dagster_home" \
    DBT_PROFILES_DIR="/app/apps/data/dbt"

# libgomp1: OpenMP runtime that lightgbm loads via ctypes at import time. The
# definitions module imports petrocast_ml, so without it Dagster fails to load
# with "libgomp.so.1: cannot open shared object file".
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends git libgomp1 && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -g 10001 app && \
    useradd -r -u 10001 -g app app

WORKDIR /app/apps/data

COPY --from=builder /app/apps/data/.venv /app/apps/data/.venv
COPY --from=builder --chown=app:app /app/apps/ml/src /app/apps/ml/src
COPY --chown=app:app data/src ./src
COPY --from=builder --chown=app:app /app/apps/data/dbt ./dbt

RUN mkdir -p "${DAGSTER_HOME}"

COPY --chown=app:app data/dagster.yaml /opt/dagster/dagster_home/dagster.yaml

RUN chown -R app:app "${DAGSTER_HOME}"

USER 10001

EXPOSE 3000

CMD ["dagster", "dev", "--host", "0.0.0.0", "--port", "3000", "--module-name", "petrocast_data.definitions"]
