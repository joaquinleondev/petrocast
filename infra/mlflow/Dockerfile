# MLflow tracking server / UI (ADR-0032, backlog F3-08).
#
# The official ghcr.io/mlflow/mlflow image ships without the Postgres driver
# and boto3, which the ADR-0032 topology needs (backend store = Postgres,
# artifact store = S3), so we build a thin image on top of python-slim.
FROM python:3.12-slim

RUN pip install --no-cache-dir \
    "mlflow==3.14.0" \
    "psycopg2-binary==2.9.12" \
    "boto3==1.43.39"

EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=12 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=4)"
