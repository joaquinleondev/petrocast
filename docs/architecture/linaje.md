# Linaje de datos navegable — F2-19

- **Backlog:** F2-19 "Linaje de datos navegable"
- **RNF:** RNF9 "Linaje de Datos" (trazabilidad) + RNF "Herramienta de Gobierno"
- **ADR de referencia:** ADR-0022 (gobierno de datos y linaje con DataHub)
- **Handoff hacia:** F2-21 (despliegue e ingesta DataHub)

## Propósito

Este documento describe cómo se construye el linaje de datos navegable en Petrocast
y cómo se prepara el handoff a DataHub (F2-21). Cumple el RNF9 que exige poder
trazar el camino de un dato desde la fuente cruda (`bronze`) hasta los dashboards
(`gold` → Metabase), y satisface el requisito de la adenda de contar con linaje
navegable a nivel de tabla.

## Las tres fuentes de linaje

DataHub (F2-21) unifica tres fuentes complementarias en un único grafo navegable:

### 1. Grafo de assets Dagster (ingesta dlt + transformación dbt)

Dagster orquesta el pipeline completo como un grafo de assets. F2-19 corrigió la
brecha de linaje entre la ingesta (dlt) y la transformación (dbt): la
`BronzeDltTranslator` (en `apps/data/src/petrocast_data/assets/dlt.py`) remapea
las claves de los assets dlt al formato `AssetKey(["bronze", <tabla>])`, que
coincide con las fuentes dbt declaradas en `apps/data/dbt/models/bronze/sources.yml`
(source `bronze`). El grafo de Dagster ahora conecta de punta a punta:

```
bronze/production_by_well ──→ silver_production ─┬──→ fact_production (gold)
                                                 ├──→ dim_company    (gold)
                                                 ├──→ dim_date       (gold)
                                                 └──→ dim_well       (gold)
bronze/wells_registry ──────→ silver_wells ──────────→ dim_well      (gold)
bronze/smoke_events ────────→ silver.smoke_events   (scaffold F2-10, sin consumidor en gold)
```

La UI de Dagster (`:3000`) expone este grafo de forma interactiva con navegación
upstream/downstream.

### 2. Artefactos dbt: `manifest.json` + `catalog.json`

`dbt docs generate` produce dos archivos en `apps/data/dbt/target/`:

| Archivo | Contenido |
|---|---|
| `manifest.json` | Grafo de dependencias entre modelos, SQL compilado, tests y metadatos |
| `catalog.json` | Tipos de columnas y estadísticas consultadas al warehouse en vivo |

Estos artefactos son el input estándar para la fuente dbt de DataHub (y para el
visor `dbt docs serve`). El directorio `target/` está en `.gitignore`; los archivos
se producen en cada ejecución, nunca se commitean.

**Generación local** (requiere warehouse levantado con bronze/silver/gold construidos):

```bash
# desde apps/data/
uv run dbt docs generate --project-dir dbt --profiles-dir dbt
```

**Visor interactivo local** (DAG de linaje dbt navegable por browser):

```bash
uv run dbt docs serve --project-dir dbt --profiles-dir dbt
```

### 3. Esquema PostgreSQL

DataHub ingiere el esquema del warehouse (tablas, columnas, tipos) directamente
desde PostgreSQL vía su conector de fuente SQL. Esto complementa el linaje dbt
con la vista física de las tablas en los schemas `bronze`, `silver` y `gold`.

## CI: exportación de artefactos

El job `data-pipeline` de `.github/workflows/ci.yml` genera y sube los artefactos
al finalizar el build gold:

```yaml
- name: Generate dbt docs (lineage artifacts)
  run: uv run dbt docs generate --project-dir dbt --profiles-dir dbt

- name: Upload dbt lineage artifacts (for DataHub / F2-21)
  uses: actions/upload-artifact@v7
  with:
    name: dbt-lineage-artifacts
    path: |
      apps/data/dbt/target/manifest.json
      apps/data/dbt/target/catalog.json
    if-no-files-found: error
```

El artefacto `dbt-lineage-artifacts` queda disponible en cada ejecución de CI
como punto de descarga para el operador de DataHub (F2-21).

## Handoff a DataHub (F2-21) — receta ilustrativa

El siguiente recipe YAML es **ilustrativo**: documenta cómo F2-21 consumirá los
artefactos para ingestar el linaje dbt en DataHub. No está conectado a ningún
servicio y no debe ejecutarse hasta que DataHub esté desplegado (F2-21).

```yaml
# Ejemplo de recipe de ingesta dbt para DataHub (F2-21 — NO operativo aún)
# Ver: https://datahubproject.io/docs/generated/ingestion/sources/dbt/
source:
  type: dbt
  config:
    # Artefactos generados por `dbt docs generate` en CI o localmente
    manifest_path: apps/data/dbt/target/manifest.json
    catalog_path: apps/data/dbt/target/catalog.json
    # Plataforma de warehouse subyacente
    target_platform: postgres
    # F2-21 ajustará y validará campos adicionales (p. ej. platform_instance,
    # inclusión de tests dbt) contra la versión de datahub-ingestion desplegada.

sink:
  type: datahub-rest
  config:
    server: "http://localhost:8080"  # GMS de DataHub (docker compose)
```

Además de esta fuente dbt, F2-21 agregará la fuente PostgreSQL para ingestar el
esquema físico del warehouse y unificar ambos en el grafo de DataHub.

## Referencias

- [ADR-0022](../adr/0022-gobierno-datos-linaje-datahub.md) — Gobierno de datos y
  linaje con DataHub (decisión de herramienta, comparación de alternativas).
- [ADR-0028](../adr/0028-orquestacion-e-ingesta-dagster-dlt.md) — Orquestación e
  ingesta Dagster/dlt (fuente del grafo de assets).
- [ADR-0023](../adr/0023-arquitectura-medallion-dbt.md) — Arquitectura medallion
  con dbt (fuente del linaje de modelos/SQL).
- [apps/data/README.md](../../apps/data/README.md#linaje-data-lineage) — Instrucciones
  de generación y visualización local.
- Backlog F2-19 (este item) y F2-21 (despliegue DataHub).
