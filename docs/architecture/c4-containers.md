# Diagrama C4 — Contenedores

```mermaid
flowchart TB
  analyst["<b>Analista / Consumidor</b><br/><i>Persona</i>"]

  subgraph boundary["Sistema Petrocast"]
    direction TB
    api["<b>API REST</b> · <i>FastAPI</i><br/>Producción + GET /api/v1/predictions<br/>(champion embebido)"]
    dagster["<b>Orquestador</b> · <i>Dagster</i><br/>Pipelines medallion + retraining_job"]
    dbt["<b>Transformaciones</b> · <i>dbt</i><br/>Bronze/Silver/Gold + schema features"]
    dw[("<b>Data Warehouse</b> · <i>PostgreSQL</i><br/>bronze / silver / gold / features")]
    mlflow["<b>Tracking + Registry</b> · <i>MLflow</i><br/>Runs, métricas, alias @champion"]
    s3[("<b>Artefactos</b> · <i>S3</i><br/>model.txt · metadata.json · evaluation.json")]
  end

  analyst -->|"HTTPS"| api
  dagster -->|"Materializa modelos"| dbt
  dbt -->|"Escribe tablas"| dw
  dagster -->|"Entrena, evalúa, promueve"| mlflow
  mlflow -->|"Guarda artefactos"| s3
  api -->|"Lee features (well_id, as_of_date)"| dw
  api -->|"Carga champion"| mlflow

  classDef person fill:#08427b,stroke:#052e56,color:#ffffff;
  classDef app fill:#1168bd,stroke:#0b4884,color:#ffffff;
  classDef db fill:#2f6f9f,stroke:#1d4c6e,color:#ffffff;
  class analyst person;
  class api,dagster,dbt,mlflow app;
  class dw,s3 db;
  style boundary fill:none,stroke:#1168bd,stroke-dasharray:5 5,color:#1168bd;
```

- **F2** — Dagster + dbt materializan las capas medallion en PostgreSQL.
- **F3** — `retraining_job` entrena LightGBM, evalúa gates y promueve el champion en MLflow; la API sirve ese champion leyendo features point-in-time del schema `features`.
