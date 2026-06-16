FROM python:3.12-slim-trixie AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY dbt ./dbt

RUN uv sync --frozen --no-dev
RUN DBT_PROFILES_DIR=/app/dbt /app/.venv/bin/dbt deps --project-dir /app/dbt --profiles-dir /app/dbt
RUN DBT_PROFILES_DIR=/app/dbt /app/.venv/bin/dbt parse --project-dir /app/dbt --profiles-dir /app/dbt

FROM python:3.12-slim-trixie AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src" \
    DAGSTER_HOME="/opt/dagster/dagster_home" \
    DBT_PROFILES_DIR="/app/dbt"

RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd -g 10001 app && \
    useradd -r -u 10001 -g app app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --chown=app:app src ./src
COPY --from=builder --chown=app:app /app/dbt ./dbt

RUN mkdir -p "${DAGSTER_HOME}"

COPY --chown=app:app dagster.yaml /opt/dagster/dagster_home/dagster.yaml

RUN chown -R app:app "${DAGSTER_HOME}"

USER 10001

EXPOSE 3000

CMD ["dagster", "dev", "--host", "0.0.0.0", "--port", "3000", "--module-name", "petrocast_data.definitions"]
