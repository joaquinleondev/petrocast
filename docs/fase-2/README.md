# README de Fase 2 — Plataforma de Datos Petrocast

Fase 2 extiende el monorepo con una **plataforma de datos end-to-end**: un
pipeline de ingesta y transformación en arquitectura medallion (bronze → silver →
gold), un data warehouse PostgreSQL 16, un gate de calidad bloqueante, dashboards
de BI en Metabase y gobierno/linaje con DataHub. Esta documentación es el punto
de entrada para un nuevo integrante o evaluador que necesite entender y operar la
plataforma completa.

---

## Arquitectura de datos

### Stack de herramientas

| Herramienta | Rol | Versión |
|---|---|---|
| **Dagster** | Orquestador de assets | 1.x |
| **dlt** | Ingesta EL (Bronze) | 1.x |
| **dbt Core** | Transformaciones SQL (Silver y Gold) | 1.x |
| **PostgreSQL** | Data warehouse (schemas `bronze`/`silver`/`gold`) | 16 |
| **Metabase OSS** | BI / dashboards de producción | v0.62 |
| **DataHub** | Catálogo de datos y linaje navegable | v1.6.0 |

### Arquitectura medallion

```
datos.gob.ar
(CSV fuente)
     │
     ▼ dlt (full-refresh por partición de mes)
 ┌────────┐
 │ BRONZE │  schemas bronze.production_by_well, bronze.wells_registry
 └────────┘
     │
     ▼ dbt build --select tag:silver  (delete+insert idempotente)
 ┌────────┐
 │ SILVER │  silver.silver_production, silver.silver_wells
 │        │  ← gate de calidad (5 dimensiones, store_failures)
 └────────┘
     │ bloqueante si falla calidad (F2-18)
     ▼ dbt build --select tag:gold  (upsert por clave de negocio)
 ┌──────┐
 │ GOLD │  fact_production + dim_well + dim_company + dim_date
 └──────┘
     │                    │
     ▼                    ▼
  API REST           Metabase :3001
  (Fase 3)           (dashboards)

 DataHub :9002 — gobierno y linaje transversal (bronze → silver → gold)
```

### Capa Bronze (F2-14)

Ingesta con dlt en modo `full-refresh` (`write_disposition="replace"`). Los
assets están particionados por mes desde `2006-01-01`; rematerializar una
partición no genera duplicados (ADR-0026).

### Capa Silver (F2-15)

Transformaciones dbt (`tag:silver`). `silver_production` usa
`delete+insert` sobre el `production_month` correspondiente a la partición,
lo que hace el reprocesamiento idempotente. `silver_wells` reconstruye el
snapshot completo en cada ejecución (ADR-0023).

### Capa Gold — star schema (F2-16)

Modelo dimensional en estrella (ADR-0024):

- `fact_production`: hechos de producción mensual con claves foráneas
  `well_key`, `company_key`, `date_key`.
- `dim_well`, `dim_company`, `dim_date`: dimensiones conformadas con
  claves subrogadas determinísticas (`dbt_utils.generate_surrogate_key`).
- Carga por **upsert** (`delete+insert` por partición de mes). SCD Tipo 1
  (sin historia en dimensiones).

### Gate de calidad (F2-17 / F2-18)

dbt corre tests de calidad sobre `silver_production` en cinco dimensiones:
schema (columnas y tipos), completitud (`not_null`), unicidad, validez de
rangos y frescura. Los fallos se persisten en `dbt_test__audit`
(`store_failures: true`). Los tests con `severity: error` se convierten en
**asset checks bloqueantes** de Dagster (`blocking=True`): si un check falla,
`gold_dbt_assets` no se ejecuta en ese run y Gold conserva el último
snapshot válido. Un sensor de fallo (`quality_block_notification`) notifica
al webhook configurado en `PETROCAST_NOTIFICATION_WEBHOOK_URL` (ADR-0025).

### Linaje (F2-19)

El grafo de Dagster conecta de punta a punta `bronze → silver → gold` a
través de la `BronzeDltTranslator`, que alinea las claves dlt con las
fuentes dbt. `dbt docs generate` produce `manifest.json` + `catalog.json`
— artefactos consumidos por DataHub. El artefacto `dbt-lineage-artifacts`
se sube en cada run de CI.

---

## Cómo correr y actualizar los workflows

### 1. Levantar el stack de datos

```bash
cp apps/data/.env.example apps/data/.env
# Editar apps/data/.env con passwords y URLs de fuentes
docker compose --env-file apps/data/.env -f infra/compose.data.yml up --build
```

Servicios disponibles:

- **Dagster UI:** <http://localhost:3000> (configurable con
  `PETROCAST_DAGSTER_PORT`)
- **PostgreSQL DW:** `localhost:5432` (configurable con
  `PETROCAST_DW_PUBLISHED_PORT`)
- **Metabase:** <http://localhost:3001> (configurable con
  `PETROCAST_METABASE_PORT`)

> Para evitar colisión de puertos con otros stacks del repo (Grafana y
> Postgres de dev también usan `:3000`/`:5432`):
>
> ```bash
> PETROCAST_DAGSTER_PORT=3001 PETROCAST_DW_PUBLISHED_PORT=5433 \
>   docker compose --env-file apps/data/.env -f infra/compose.data.yml up
> ```

### 2. Materializar assets desde la UI de Dagster

En <http://localhost:3000>, navegar a **Assets** y seleccionar los assets a
materializar. Para materializar el pipeline completo de un mes:

1. Seleccionar `bronze/production_by_well` y `bronze/wells_registry` →
   **Materialize** con partición de mes deseada.
2. Seleccionar `silver/silver_dbt_assets` → **Materialize** con la misma
   partición.
3. Seleccionar `gold/gold_dbt_assets` → **Materialize** con la misma
   partición.

El linaje en el grafo de Dagster muestra las dependencias upstream/downstream
entre assets.

### 3. Materializar assets desde la CLI

```bash
# Smoke path (verificar el stack)
uv run dagster asset materialize \
  --module-name petrocast_data.definitions \
  --select "warehouse_schemas_ready,bronze/smoke_events"

# Bronze — ingesta de un mes específico
uv run dagster asset materialize \
  --module-name petrocast_data.definitions \
  --select "bronze/production_by_well,bronze/wells_registry" \
  --partition 2026-05-01

# Silver — build + calidad
uv run dbt build --project-dir dbt --profiles-dir dbt --select tag:silver

# Gold — star schema
uv run dbt build --project-dir dbt --profiles-dir dbt --select tag:gold
```

Todos los comandos dbt se ejecutan desde `apps/data/`. Para un rango
histórico de meses (backfill), ver [`docs/runbooks/`](../runbooks/).

### 4. Cómo agrega/modifica assets un desarrollador

- **Nuevo asset dlt (Bronze):** agregar la fuente en
  `apps/data/src/petrocast_data/assets/` con `@dlt_assets` y declarar la
  fuente en `apps/data/dbt/models/bronze/sources.yml` para que Silver pueda
  hacer `ref()`.
- **Nuevo modelo dbt (Silver/Gold):** agregar el archivo `.sql` bajo
  `apps/data/dbt/models/silver/` o `apps/data/dbt/models/gold/` con el tag
  correspondiente (`tag:silver` / `tag:gold`).
- **Nuevo test de calidad:** declararlo en el `.yml` del modelo Silver con
  `severity: error` para que sea bloqueante, o `severity: warn` para
  advertencia no bloqueante.

Para detalles de configuración de entorno, variables y procedimientos de
backfill, ver [`apps/data/README.md`](../../apps/data/README.md).

### 5. Pipeline CI (`data-pipeline` job)

El job `data-pipeline` de `.github/workflows/ci.yml` valida el pipeline
completo en cada PR y push a `main`:

```
pytest (data app)
  → dagster asset materialize --select "warehouse_schemas_ready,bronze/smoke_events"
  → dagster asset materialize --select "bronze/production_by_well,bronze/wells_registry"
  → dbt build --select tag:f2_10_scaffold
  → dbt build --select tag:silver
  → dbt build --select tag:gold
  → dbt docs generate  (→ artefacto dbt-lineage-artifacts)
```

Las dos llamadas a `materialize` son secuenciales (no se usa `--select "*"`)
para evitar un deadlock de dlt al escribir concurrentemente en el schema
`bronze`. Los selectors dbt usan la notación `tag:<capa>` (slash-notation en
Dagster: `bronze/...`, `silver/...`, `gold/...`).

---

## Acceso a BI — Metabase

Metabase OSS arranca automáticamente con `compose.data.yml`. **Puerto
host: `:3001`** (para no colisionar con Dagster en `:3000`).

### Levantar y provisionar

```bash
# 1. Levantar el stack (Metabase incluido)
docker compose --env-file apps/data/.env -f infra/compose.data.yml up -d

# 2. Provisionar dashboards (idempotente — se puede re-ejecutar)
PETROCAST_METABASE_ADMIN_EMAIL=admin@example.com \
PETROCAST_METABASE_ADMIN_PASSWORD=secreto \
PETROCAST_BI_DB_PASSWORD=change-me \
python3 infra/metabase/provision_metabase.py
```

El script de provisioning crea la conexión de solo lectura al schema `gold`
con el usuario `petrocast_bi` y genera el dashboard **"Producción Petrocast"**
con tres tarjetas (producción por pozo/mes, evolución histórica mensual, top
pozos por volumen) y filtros de Pozo, Fecha y Tipo de fluido.

### Modelo de acceso

- Usuario de DW: `petrocast_bi` — `SELECT` solo en el schema `gold`
  (sin acceso a `bronze` ni `silver`).
- Credenciales de admin de Metabase: definidas en
  `PETROCAST_METABASE_ADMIN_EMAIL` / `PETROCAST_METABASE_ADMIN_PASSWORD`.

Para el runbook completo (operaciones, re-sync de tablas, producción con
Postgres en lugar de H2), ver [`infra/metabase/README.md`](../../infra/metabase/README.md).

---

## Acceso a Gobierno — DataHub

DataHub es **on-demand** (consume ~6 contenedores y ~4 GB de RAM); no está
en el path always-on. Levantarlo solo para catalogar o explorar el linaje.

**Puerto host: `:9002`** — usuario/password: `datahub` / `datahub`.

### Ciclo de vida básico

```bash
# 1. Generar artefactos dbt (requiere warehouse levantado con Bronze/Silver/Gold)
cd apps/data
uv run dbt docs generate --project-dir dbt --profiles-dir dbt

# 2. Levantar el stack DataHub
docker compose --env-file apps/data/.env -f infra/compose.datahub.yml up -d

# 3. Ingestar metadatos (linaje dbt + esquema PostgreSQL)
infra/datahub/datahub.sh ingest

# 4. Navegar en http://localhost:9002  (datahub / datahub)

# 5. Bajar el stack (liberar RAM)
infra/datahub/datahub.sh down
```

En la UI de DataHub:

- **Catálogo:** Browse > Datasets > postgres > petrocast > gold/silver/bronze.
- **Linaje:** abrir cualquier tabla > pestaña "Lineage" > upstream/downstream.
- **Row counts:** Dataset > pestaña "Profiling".

Para el runbook completo (variables de entorno, versión pinneada, recetas
de ingesta individuales), ver
[`infra/datahub/README.md`](../../infra/datahub/README.md).

---

## Mapa de documentación

| Documento | Qué cubre |
|---|---|
| [`apps/data/README.md`](../../apps/data/README.md) | Guía profunda: configuración, Bronze/Silver/Gold, calidad, consecuencia, linaje, Metabase |
| [`docs/architecture/linaje.md`](../architecture/linaje.md) | Diseño del linaje navegable: grafo Dagster, artefactos dbt, handoff a DataHub |
| [`docs/architecture/c4-context.md`](../architecture/c4-context.md) | Diagrama C4 de contexto del sistema |
| [`docs/architecture/c4-containers.md`](../architecture/c4-containers.md) | Diagrama C4 de contenedores |
| [`docs/runbooks/`](../runbooks/) | Runbooks operativos (backfill, data engineer, etc.) |
| [`docs/adr/README.md`](../adr/README.md) | Índice completo de ADRs |
| [`docs/fase-3/README.md`](../fase-3/README.md) | Vertical de ML de Fase 3 (arquitectura, cómo correr, guion de video) |

### ADRs relevantes para Fase 2

| ADR | Título |
|---|---|
| [ADR-0022](../adr/0022-gobierno-datos-linaje-datahub.md) | Gobierno de datos y linaje con DataHub |
| [ADR-0023](../adr/0023-arquitectura-medallion-dbt.md) | Arquitectura medallion y motor dbt Core v2 |
| [ADR-0024](../adr/0024-modelo-dimensional-star-schema.md) | Modelo dimensional gold (star schema) |
| [ADR-0025](../adr/0025-calidad-datos-consecuencia.md) | Calidad de datos y consecuencia operativa |
| [ADR-0026](../adr/0026-tipo-carga-medallion.md) | Tipo de carga por capa medallion |
| [ADR-0028](../adr/0028-orquestacion-e-ingesta-dagster-dlt.md) | Orquestación con Dagster e ingesta con dlt |
| [ADR-0029](../adr/0029-plataforma-bi-metabase.md) | Plataforma de BI con Metabase OSS |

---

## Requisitos no funcionales de Fase 2

La adenda de Fase 2 define dos RNF que esta plataforma implementa:

- **RNF1 — Linaje de Datos (RNF9):** trazabilidad completa desde la fuente
  cruda hasta los dashboards, navegable a nivel de tabla vía DataHub
  (ADR-0022, F2-19/F2-21).
- **RNF2 — Herramienta de Gobierno:** catálogo de datos con metadatos,
  descripciones de columnas y row counts, provisto por DataHub v1.6.0.
