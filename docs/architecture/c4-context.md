# Diagrama C4 — Contexto del sistema

Petrocast a través de las tres fases: ingesta y datos (F2), pronóstico ML (F3) y
API pública (F1+F3).

```mermaid
C4Context
  title Contexto — Petrocast
  Person(analyst, "Analista / Consumidor", "Consulta producción y pronósticos")
  System(petrocast, "Petrocast", "Plataforma de datos + pronóstico de producción")
  System_Ext(datagov, "datos.gob.ar", "Fuente pública de producción de hidrocarburos")
  System_Ext(mlflow, "MLflow", "Tracking y registry de modelos (backend Postgres + S3)")
  Rel(analyst, petrocast, "Consulta API REST / BI")
  Rel(petrocast, datagov, "Ingesta datos de producción")
  Rel(petrocast, mlflow, "Loguea runs, promueve champion")
```

- **Fase 1** — API REST + observabilidad + despliegue AWS.
- **Fase 2** — plataforma de datos medallion (Bronze/Silver/Gold) con dbt + Dagster.
- **Fase 3** — vertical ML: feature store, entrenamiento, gates, registry y serving.
