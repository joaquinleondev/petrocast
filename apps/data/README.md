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

## Bronze ingestion

F2-14 suma la ingesta real de las dos fuentes oficiales de datos.gob.ar:

- `production_by_well`: producción mensual por pozo no convencional.
- `wells_registry`: listado complementario de pozos cargados por operadoras.

Ambas tablas se cargan con `dlt` en el schema `bronze` usando full refresh
(`write_disposition="replace"`), alineado con ADR-0026. Los assets están
particionados por mes desde `2006-01-01`; la partición representa el mes
operativo del snapshot Bronze y se puede rematerializar desde la UI de Dagster
sin duplicar filas.

Las variables `PETROCAST_SOURCE_PRODUCTION_URL` y `PETROCAST_SOURCE_WELLS_URL`
aceptan URLs de página `datos.gob.ar/archivo/...`, URLs CSV directas o paths
locales. En CI se usan fixtures locales para validar el camino dlt/Dagster sin
depender de internet.

## Silver transform

F2-15 agrega la transformación Bronze → Silver con dbt (tipado, normalización y
nombres en inglés), alineada con ADR-0023 y ADR-0026:

- `silver_production` (incremental, `delete+insert`): producción mensual por
  pozo, un registro por `(well_id, production_month)`. El mes se deriva de los
  datos (`anio`/`mes`), **no** del tag de partición de Bronze. Rematerializar un
  mes es idempotente porque el `delete+insert` reconstruye toda la partición de
  ese `production_month`.
- `silver_wells` (`table`): listado complementario de pozos normalizado al
  snapshot vigente (un registro por `well_id`). Sin grano mensual.

El asset de Dagster `silver_dbt_assets` está particionado por mes (desde
`2006-01-01`) y pasa la ventana de la partición a dbt como `min_month`/`max_month`.

### Backfill por rango de meses

Rematerializar un rango de meses (p. ej. tras una corrección histórica en la
fuente) es idempotente. Por CLI dbt directamente:

```bash
uv run dbt build --project-dir dbt --profiles-dir dbt --select tag:silver \
  --vars '{"min_month": "2016-01-01", "max_month": "2016-04-01"}'
```

Sin `min_month`/`max_month` se reconstruye el snapshot completo. Desde Dagster,
rematerializar el rango de particiones de mes ejecuta el mismo `delete+insert`
por cada mes (el procedimiento formal de backfill se documenta en F2-23/F2-26).

## Gold star schema

F2-16 agrega la capa Gold con un modelo dimensional en estrella, alineado con
ADR-0024 y ADR-0026:

- `fact_production`: tabla de hechos de producción mensual, con grano de un
  registro por pozo y mes (`well_id` × `production_month`). Mide
  `oil_prod_m3`, `gas_prod_mm3` y `water_prod_m3`, y expone las claves foráneas
  `well_key`, `company_key` y `date_key`.
- `dim_well`, `dim_company`, `dim_date`: dimensiones conformadas (pozo, empresa
  y mes). El universo de `dim_well` es la unión de los pozos de `silver_wells` y
  `silver_production`, de modo que todo pozo del hecho tiene su fila de dimensión
  (sin huecos de FK).

Las claves subrogadas se generan con `dbt_utils.generate_surrogate_key` (hash
determinístico) sobre las claves de negocio. La misma expresión de hash se usa
en el hecho y en las dimensiones, así las claves foráneas resuelven los joins.
Las dimensiones aplican **SCD Tipo 1** (overwrite): no se conserva historia.

La carga es un **upsert por clave de negocio** vía dbt incremental con
`delete+insert` (equivalente seguro en PostgreSQL a `on conflict do update`):
reconstruye la partición correspondiente y la vuelve a insertar, por lo que
reprocesar es idempotente y no genera duplicados.

El asset de Dagster `gold_dbt_assets` está particionado por mes (desde
`2006-01-01`, igual que Silver) y pasa la ventana de la partición a dbt como
`min_month`/`max_month`. `fact_production` aplica ese mismo filtro de rango de
meses, por lo que el backfill por rango funciona con el mismo mecanismo que
Silver:

```bash
uv run dbt build --project-dir dbt --profiles-dir dbt --select tag:gold \
  --vars '{"min_month": "2016-01-01", "max_month": "2016-04-01"}'
```

## Calidad de datos

F2-17 agrega chequeos de calidad sobre la transición **Bronze → Silver**
(`silver_production`), alineado con ADR-0025. Cubre cinco dimensiones:

- **Schema**: `contract: enforced` valida columnas y tipos esperados en build.
- **Completitud**: `not_null` en claves (`well_id`, `company_id`,
  `production_month`) y `dbt_utils.not_null_proportion` (umbral) en las medidas.
- **Unicidad**: `dbt_utils.unique_combination_of_columns` sobre
  `(well_id, production_month)`.
- **Validez de rangos**: `dbt_utils.accepted_range` (`oil_prod_m3`,
  `gas_prod_mm3`, `water_prod_m3` ≥ 0; `production_month` ≥ 2006-01-01).
- **Frescura**: `dbt_utils.recency` sobre `production_month` (severidad `warn`;
  el bloqueo ante datos viejos se define en F2-18).

Los resultados quedan **persistidos**: `store_failures: true` (en
`dbt_project.yml`) escribe las filas que fallan en el schema `dbt_test__audit`
(una tabla por test), no solo un pass/fail en runtime. Esa evidencia la consumen los runbooks de Data Owner y
Data Engineer (F2-26/F2-27). La **consecuencia operativa** (bloqueo de
promoción + notificación) se implementa en F2-18.

Los tests corren con `dbt build` (incluido en CI):

```bash
uv run dbt build --project-dir dbt --profiles-dir dbt --select tag:silver
```

## Nota sobre dbt v2 / Fusion

El proyecto queda integrado a Dagster mediante `dagster-dbt`. Para que el smoke
path funcione contra PostgreSQL, este scaffold usa `dbt-postgres` estable. La
migración al runtime dbt Core v2/Fusion queda localizada en la dependencia del
CLI dbt cuando el adapter de PostgreSQL esté disponible en esa línea.
