# Diagrama C4 — Contexto del sistema

Petrocast a través de las tres fases: ingesta y datos (F2), pronóstico ML (F3) y
API pública (F1+F3).

```mermaid
flowchart LR
  analyst["<b>Analista / Consumidor</b><br/><i>Persona</i><br/>Consulta producción y pronósticos"]

  subgraph boundary["Sistema Petrocast"]
    petrocast["<b>Petrocast</b><br/><i>Plataforma de datos +<br/>pronóstico de producción</i>"]
  end

  datagov["<b>datos.gob.ar</b><br/><i>Sistema externo</i><br/>Producción pública de hidrocarburos"]
  mlflow["<b>MLflow</b><br/><i>Sistema externo</i><br/>Tracking + registry de modelos<br/>(backend Postgres + S3)"]

  analyst -->|"Consulta API REST / BI"| petrocast
  petrocast -->|"Ingesta producción"| datagov
  petrocast -->|"Loguea runs, promueve champion"| mlflow

  classDef person fill:#08427b,stroke:#052e56,color:#ffffff;
  classDef system fill:#1168bd,stroke:#0b4884,color:#ffffff;
  classDef ext fill:#7a8288,stroke:#565c61,color:#ffffff;
  class analyst person;
  class petrocast system;
  class datagov,mlflow ext;
  style boundary fill:none,stroke:#1168bd,stroke-dasharray:5 5,color:#1168bd;
```

- **Fase 1** — API REST + observabilidad + despliegue AWS.
- **Fase 2** — plataforma de datos medallion (Bronze/Silver/Gold) con dbt + Dagster.
- **Fase 3** — vertical ML: feature store, entrenamiento, gates, registry y serving.
