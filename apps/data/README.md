# Petrocast Data Stack

Scaffold de Fase 2 para el pipeline de datos:

- PostgreSQL 16 como data warehouse con schemas `bronze`, `silver` y `gold`.
- Dagster como orquestador con UI en `:3000`.
- dbt integrado desde Dagster mediante `dagster-dbt`.
- dlt integrado desde Dagster mediante `dagster-dlt`.

## Ejecutar

Desde la raíz del repo:

```bash
cp apps/data/.env.example apps/data/.env
docker compose --env-file apps/data/.env -f infra/compose.data.yml up --build
```

Servicios:

- Dagster UI: <http://localhost:3000>
- PostgreSQL: `localhost:5432`

Los puertos publicados en el host son configurables para convivir con los
otros stacks del repo (Grafana también usa el 3000; el Postgres de
`compose.dev.yml`, el 5432):

```bash
PETROCAST_DAGSTER_PORT=3001 PETROCAST_DW_PUBLISHED_PORT=5433 \
  docker compose --env-file apps/data/.env -f infra/compose.data.yml up
```

## Configuración

El stack de datos lee su configuración desde variables de entorno, alineado con
ADR-0018. El archivo versionado `apps/data/.env.example` documenta todas las
variables esperadas; los secretos reales deben vivir fuera del repo, en
`apps/data/.env` local o en GitHub Secrets para ambientes remotos.

Variables principales:

- `PETROCAST_DW_*`: conexión al data warehouse PostgreSQL.
- `PETROCAST_SOURCE_PRODUCTION_URL`: fuente de producción mensual por pozo.
- `PETROCAST_SOURCE_WELLS_URL`: fuente complementaria de listado de pozos.
- `PETROCAST_NOTIFICATION_WEBHOOK_URL`: webhook opcional para notificaciones.

Dentro de Docker Compose, Dagster usa `data-postgres` como host interno del
warehouse. Para comandos locales fuera de Compose, usá `PETROCAST_DW_HOST=localhost`
o exportá las variables desde `apps/data/.env`.

Si cambiás `PETROCAST_DW_PASSWORD` después de haber creado el volumen local de
Postgres, recreá el volumen para que la credencial se aplique:

```bash
docker compose --env-file apps/data/.env -f infra/compose.data.yml down -v
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
