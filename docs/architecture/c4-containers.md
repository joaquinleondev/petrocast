# Diagrama C4 — Contenedores

```mermaid
C4Container
  title Contenedores — Petrocast (F1+F2+F3)
  Person(analyst, "Analista / Consumidor")
  Container(api, "API REST", "FastAPI", "Endpoints de producción y GET /api/v1/predictions (champion embebido)")
  Container(dagster, "Orquestador", "Dagster", "Pipelines medallion + retraining_job ML")
  Container(dbt, "Transformaciones", "dbt", "Bronze/Silver/Gold + schema features")
  ContainerDb(dw, "Data Warehouse", "PostgreSQL", "Schemas bronze/silver/gold/features")
  Container(mlflow, "Tracking + Registry", "MLflow", "Runs, métricas, alias @champion")
  ContainerDb(s3, "Artefactos", "S3", "model.txt, metadata.json, evaluation.json")
  Rel(analyst, api, "HTTPS")
  Rel(api, dw, "Lee features por (well_id, as_of_date)")
  Rel(api, mlflow, "Carga models:/petrocast-production@champion")
  Rel(dagster, dbt, "Materializa modelos")
  Rel(dbt, dw, "Escribe tablas")
  Rel(dagster, mlflow, "Entrena, evalúa, promueve")
  Rel(mlflow, s3, "Guarda artefactos")
```

- **F2** — Dagster + dbt materializan las capas medallion en PostgreSQL.
- **F3** — `retraining_job` entrena LightGBM, evalúa gates y promueve el champion en MLflow; la API sirve ese champion leyendo features point-in-time del schema `features`.
