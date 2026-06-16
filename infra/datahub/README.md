# DataHub — Gobierno de Datos y Linaje (F2-21)

> Implementa **ADR-0022** y los RNF "Linaje de Datos" y "Herramienta de
> Gobierno" (adenda Fase 2). DataHub permite navegar el linaje a nivel de
> tabla **bronze → silver → gold**, ver el catálogo del DW físico y explorar
> las relaciones entre modelos dbt y tablas PostgreSQL.

## Arquitectura de linaje

```
dbt manifest.json          Postgres DW
(F2-19 artifact)           bronze / silver / gold
       │                          │
       └──────────┬───────────────┘
                  ▼
           DataHub GMS (ingesta)
                  │
           DataHub UI — linaje navegable a nivel tabla
                  upstream ← tabla → downstream
```

DataHub unifica dos fuentes complementarias:

| Fuente | Qué aporta |
|--------|-----------|
| **dbt** (F2-19) | Grafo de dependencias entre modelos SQL (`manifest.json`), descripciones de columnas (`catalog.json`), tests como assertions |
| **PostgreSQL** | Schema físico de cada tabla (bronze/silver/gold), row counts via profiling, vistas |

## Dependencia F2-19

Los artefactos de linaje dbt (`manifest.json` + `catalog.json`) son
producidos por `dbt docs generate` — funcionalidad de **F2-19 (PR #78)**.
Sin esos archivos la receta `dbt.yml` falla con "file not found".

Verificar que F2-19 esté mergeado antes de correr la ingesta dbt, o
generarlos manualmente:

```bash
cd apps/data
uv run dbt docs generate --project-dir dbt --profiles-dir dbt
```

## Ciclo de vida on-demand

DataHub consume ~6 contenedores y ~4 GB de RAM — **no está en el path
always-on**. Levantarlo solo cuando haya que catalogar/explorar el linaje.

### Paso 1 — Generar artefactos dbt (requiere F2-19)

```bash
# Desde apps/data/, con el DW corriendo (compose.data.yml)
uv run dbt docs generate --project-dir dbt --profiles-dir dbt
```

Esto produce `apps/data/dbt/target/manifest.json` y `catalog.json`.

### Paso 2 — Levantar el stack DataHub

```bash
docker compose --env-file apps/data/.env \
    -f infra/compose.datahub.yml up -d
```

Esperar a que los healthchecks estén todos `healthy` (~2-3 min):

```bash
docker compose -f infra/compose.datahub.yml ps
```

### Paso 3 — Ingestar metadatos

Instalar el CLI de DataHub (no requiere entorno de Python propio — `uvx`
lo descarga al vuelo):

```bash
# Ingesta del linaje dbt (F2-19 requerido)
uvx --from 'acryl-datahub[dbt,datahub-rest]' \
    datahub ingest -c infra/datahub/recipes/dbt.yml

# Ingesta del DW físico (esquemas bronze/silver/gold + row counts)
uvx --from 'acryl-datahub[postgres,datahub-rest]' \
    datahub ingest -c infra/datahub/recipes/postgres.yml
```

O usar el script helper (ver abajo):

```bash
infra/datahub/datahub.sh ingest
```

### Paso 4 — Navegar el catálogo y el linaje

Abrir `http://localhost:9002` (user: `datahub` / pass: `datahub`).

- **Catálogo:** Browse > Datasets > postgres > petrocast > gold/silver/bronze
- **Linaje:** abrir cualquier tabla > pestaña "Lineage" > upstream/downstream
- **Row counts:** Dataset > pestaña "Profiling" > Row Count (actualizado en
  cada corrida de la receta postgres con `profiling.enabled: true`)
- **Última actualización:** el campo "Last Ingested" en DataHub refleja el
  timestamp de la última corrida de la receta. Para ver la frescura real del
  dato correlacionar con los runs de Dagster (F2-15/F2-16).

### Paso 5 — Bajar el stack (liberar RAM)

```bash
docker compose -f infra/compose.datahub.yml down
# Para borrar también los volúmenes (reset completo):
docker compose -f infra/compose.datahub.yml down -v
```

## Script helper

```bash
infra/datahub/datahub.sh up      # Levanta el stack en background
infra/datahub/datahub.sh ingest  # Corre ambas recetas (dbt + postgres)
infra/datahub/datahub.sh down    # Baja el stack
infra/datahub/datahub.sh status  # Estado de los contenedores
```

## Variables de entorno

Todas tienen defaults seguros para desarrollo local. Configurar en
`apps/data/.env` para sobreescribir:

| Variable | Default | Descripción |
|----------|---------|-------------|
| `PETROCAST_DATAHUB_PORT` | `9002` | Puerto host de la UI de DataHub |
| `PETROCAST_DATAHUB_GMS_PORT` | `8080` | Puerto host del GMS REST API |
| `PETROCAST_DATAHUB_GMS` | `http://localhost:8080` | URL del GMS (usada por las recetas CLI) |
| `PETROCAST_DATAHUB_SIGNING_KEY` | `datahub-signing-key-change-for-prod` | Clave HMAC para tokens |
| `PETROCAST_DATAHUB_SIGNING_SALT` | `datahub-signing-salt-change-for-prod` | Salt para tokens |
| `PETROCAST_DATAHUB_SECRET` | `datahub-secret-change-for-prod` | Secret del frontend Play |
| `PETROCAST_DATAHUB_MYSQL_ROOT_PASSWORD` | `datahub` | Root password de MySQL interno |

Las variables `PETROCAST_DW_*` son compartidas con `compose.data.yml`.

## Row counts y "última actualización"

- **Row counts:** la receta `postgres.yml` tiene `profiling.enabled: true`.
  Esto ejecuta `COUNT(*)` (y estadísticas de columnas) en cada corrida. El
  resultado es visible en DataHub UI > Dataset > Profiling > Row Count.
  Para actualizar: re-correr la receta postgres.

- **Última actualización / frescura:** DataHub muestra "Last Ingested" (cuándo
  corrió la receta), no cuándo cambió el dato. Para trazar la frescura real:
  1. Ver los runs de Dagster (F2-15 silver, F2-16 gold) en `http://localhost:3000`
  2. O configurar un Dataset Assertion de tipo `freshness` en DataHub (avanzado).

## Versión pinneada

DataHub **v1.6.0** (mayo 2026).
Fuente: <https://hub.docker.com/r/acryldata/datahub-gms/tags>

Imágenes:

- `acryldata/datahub-gms:v1.6.0`
- `acryldata/datahub-frontend-react:v1.6.0`
- `acryldata/datahub-actions:v1.6.0-slim`
- `acryldata/datahub-upgrade:v1.6.0`
- `opensearchproject/opensearch:2.19.3` (reemplaza Elasticsearch en v1.x)
- `confluentinc/cp-kafka:8.0.0` (KRaft — sin Zookeeper)
- `mysql:8.2` (metadata store)

## Referencias

- ADR-0022: Gobierno de datos y linaje con DataHub
- RNF "Linaje de Datos" y "Herramienta de Gobierno" (adenda Fase 2)
- F2-19 (PR #78): ingesta de artefactos dbt — prerequisito para `dbt.yml`
- F2-21 (Issue #33): esta implementación
