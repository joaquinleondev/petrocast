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
por cada mes. El procedimiento formal está en
[`docs/runbooks/backfill.md`](../../docs/runbooks/backfill.md).

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

## Consecuencia operativa: bloqueo + notificación

F2-18 le da **consecuencia** a la calidad de F2-17, alineado con ADR-0025: un
dato malo no solo se marca, **bloquea la promoción a Gold** y **avisa**.

- **Bloqueo (asset checks bloqueantes).** `dagster-dbt` expone cada test dbt de
  `silver_production` como un *asset check* de Dagster. Los tests de integridad y
  validez corren con la severidad por defecto de dbt (`error`), por lo que sus
  checks son **bloqueantes** (`blocking=True`); el de frescura (`recency`) es
  `warn`, así que avisa pero no bloquea. Cuando un check bloqueante falla, el
  `dbt build` de Silver termina con error y el step `silver_dbt_assets` falla;
  como Gold hace `ref()` de Silver, Dagster **no ejecuta** `gold_dbt_assets` en
  ese run. En la UI se ve el step de Silver en rojo, el check fallido, y Gold
  saltado (`Dependencies for step gold_dbt_assets failed ... Not executing`).
- **Estado visible.** Los checks (pasa/falla, severidad y filas fallidas vía
  `store_failures`) son navegables en la UI de Dagster sobre el asset
  `silver/silver_production`.
- **Notificación.** El sensor `quality_block_notification` (un
  `@run_failure_sensor`) se dispara cuando un run falla; si el fallo incluye
  checks de calidad, postea al webhook configurado en
  `PETROCAST_NOTIFICATION_WEBHOOK_URL` (Slack/email) un payload con el run, el job
  y la lista de checks fallidos. Si la variable está vacía (CI/local), el sensor
  **no hace nada** en vez de fallar.
- **Gold conserva el último valor válido.** Como Gold no se materializa ante un
  bloqueo, sus tablas quedan **intactas** con el último snapshot válido (la carga
  es `delete+insert` por partición y solo corre si Silver pasó). Por eso Metabase
  (F2-20), que lee de `gold`, sigue mostrando el último Gold bueno mientras dura
  el bloqueo, en lugar de exponer datos corruptos.

Probar el camino de falla localmente (resumen; el procedimiento formal vive en
F2-23/F2-30): cargar Bronze, materializar Silver+Gold de una partición con datos
(p. ej. `2016-01-01`) y verificar que pasan; inyectar una violación en Bronze
(p. ej. `update bronze.production_by_well set prod_pet = '-5.000'`), re-materializar
el mismo run y verificar que el check `accepted_range` de `oil_prod_m3` falla y que
`gold.fact_production` **no cambia**.

## Linaje (data lineage)

F2-19 conecta el grafo de assets de Dagster de punta a punta (`bronze → silver →
gold`) y habilita la generación de artefactos de linaje para DataHub (F2-21).

### Grafo de assets Dagster (bronze → silver → gold)

La `BronzeDltTranslator` en `src/petrocast_data/assets/dlt.py` remapea las claves
de los assets dlt al formato `["bronze", <tabla>]`, que coincide con la fuente dbt
(`sources.yml`, source `bronze`). El resultado: los assets `bronze/production_by_well`,
`bronze/wells_registry` y `bronze/smoke_events` aparecen en el grafo de Dagster como
upstream de los modelos silver y gold; el linaje completo es navegable desde la UI de
Dagster en <http://localhost:3000> (o el puerto configurado con `PETROCAST_DAGSTER_PORT`).

### Generar artefactos de linaje dbt localmente

Requiere el warehouse levantado y las capas bronze/silver/gold ya construidas
(seguí los pasos de **Ejecutar** y **Bronze ingestion** de este README).

```bash
# desde apps/data/
uv run dbt docs generate --project-dir dbt --profiles-dir dbt
```

Esto genera `apps/data/dbt/target/manifest.json` (grafo de modelos + SQL compilado)
y `apps/data/dbt/target/catalog.json` (tipos de columnas desde el warehouse). El
directorio `target/` está en `.gitignore`; los artefactos se producen, nunca se
commitean.

### Navegar el DAG de linaje dbt

```bash
# desde apps/data/
uv run dbt docs serve --project-dir dbt --profiles-dir dbt
```

Abre el navegador en el sitio de dbt docs: un visor interactivo del DAG bronze →
silver → gold donde podés explorar cada modelo, su SQL compilado y sus dependencias
upstream/downstream.

### Artefactos de handoff a DataHub (F2-21)

El par `manifest.json` + `catalog.json` es el input para la fuente dbt de DataHub
(recipe de ingesta). CI los genera después del build gold y los sube como artefacto
`dbt-lineage-artifacts` (ver `.github/workflows/ci.yml`). El procedimiento completo
de ingesta en DataHub se documenta en
[`docs/architecture/linaje.md`](../../docs/architecture/linaje.md).

## Nota sobre dbt v2 / Fusion

El proyecto queda integrado a Dagster mediante `dagster-dbt`. Para que el smoke
path funcione contra PostgreSQL, este scaffold usa `dbt-postgres` estable. La
migración al runtime dbt Core v2/Fusion queda localizada en la dependencia del
CLI dbt cuando el adapter de PostgreSQL esté disponible en esa línea.
