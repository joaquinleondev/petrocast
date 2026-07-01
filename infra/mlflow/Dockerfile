# MLflow tracking server / UI (ADR-0032, backlog F3-08).
#
# The official ghcr.io/mlflow/mlflow image ships without the Postgres driver
# and boto3, which the ADR-0032 topology needs (backend store = Postgres,
# artifact store = S3), so we build a thin image on top of python-slim.
FROM python:3.12-slim

RUN pip install --no-cache-dir \
    "mlflow>=3.1,<4" \
    "psycopg2-binary>=2.9" \
    "boto3>=1.34"

EXPOSE 5000
