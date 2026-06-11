# Petrocast Data Stack

Scaffold de Fase 2 para el pipeline de datos:

- PostgreSQL 16 como data warehouse con schemas `bronze`, `silver` y `gold`.
- Dagster como orquestador con UI en `:3000`.
- dbt integrado desde Dagster mediante `dagster-dbt`.
- dlt integrado desde Dagster mediante `dagster-dlt`.

## Ejecutar

Desde la raíz del repo:

```bash
docker compose -f infra/compose.data.yml up --build
```

Servicios:

- Dagster UI: <http://localhost:3000>
- PostgreSQL: `localhost:5432`

Los puertos publicados en el host son configurables para convivir con los
otros stacks del repo (Grafana también usa el 3000; el Postgres de
`compose.dev.yml`, el 5432):

```bash
PETROCAST_DAGSTER_PORT=3001 PETROCAST_DW_PUBLISHED_PORT=5433 \
  docker compose -f infra/compose.data.yml up
```

## Smoke path

En Dagster, materializá estos assets:

1. `warehouse_schemas_ready`: asegura los schemas medallion.
2. `petrocast_smoke`: carga una tabla de prueba con dlt en `bronze`.
3. `smoke_events`: ejecuta dbt sobre el modelo de prueba en `silver`.

Este PR sólo crea el scaffold. La ingesta real de las fuentes de datos.gob.ar se
implementa en F2-14.

## Nota sobre dbt v2 / Fusion

El proyecto queda integrado a Dagster mediante `dagster-dbt`. Para que el smoke
path funcione contra PostgreSQL, este scaffold usa `dbt-postgres` estable. La
migración al runtime dbt Core v2/Fusion queda localizada en la dependencia del
CLI dbt cuando el adapter de PostgreSQL esté disponible en esa línea.
