# Procedimiento de backfill histórico

## Propósito y alcance

Este procedimiento permite reprocesar un rango histórico de meses cuando cambia
la fuente, se corrige un dato en `bronze` o se necesita reconstruir `silver` y
`gold` para una ventana específica.

El reproceso siempre parte desde `bronze`:

1. Se refresca el snapshot crudo con `dlt` (`write_disposition="replace"`).
2. Se rematerializa el rango mensual en `silver`.
3. Se rematerializa el mismo rango en `gold`.
4. Los asset checks de calidad bloquean la promoción si el dato no es apto.

La partición mensual representa el primer día del mes (`YYYY-MM-01`). En el CLI,
`--partition-range 2016-01-01...2016-03-01` incluye enero, febrero y marzo de
2016; internamente dbt procesa `production_month >= 2016-01-01` y
`production_month < 2016-04-01`.

## Prerrequisitos

- Branch actualizada con `main`.
- Stack de datos levantado o Postgres 16 accesible.
- Variables `PETROCAST_DW_*`, `PETROCAST_SOURCE_PRODUCTION_URL` y
  `PETROCAST_SOURCE_WELLS_URL` configuradas.
- `dbt deps` y `dbt parse` ejecutados antes de cargar las definiciones de
  Dagster, para que exista `apps/data/dbt/target/manifest.json`.

Desde la raíz del repo:

```bash
cp apps/data/.env.example apps/data/.env
docker compose --env-file apps/data/.env -f infra/compose.data.yml up --build
```

Para correr comandos locales desde `apps/data`:

```bash
cd apps/data
export PYTHONPATH="$PWD/src"
uv run dbt deps --project-dir dbt
uv run dbt parse --project-dir dbt --profiles-dir dbt
```

## Procedimiento desde la UI de Dagster

1. Abrir <http://localhost:3000>.
2. Entrar en **Assets** y verificar que el código cargó sin errores.
3. Materializar `warehouse_schemas_ready` si el DW es nuevo o fue recreado.
4. Materializar los assets Bronze:
   - `dlt_petrocast_bronze_production_by_well`
   - `dlt_petrocast_bronze_wells_registry`
5. Elegir una partición operativa para Bronze, por ejemplo `2026-05-01`.
   Bronze es full refresh: no filtra por mes de producción, solo guarda el
   snapshot crudo vigente.
6. Seleccionar los assets transformacionales:
   - `silver/silver_production`
   - `silver/silver_wells`
   - `gold/dim_company`
   - `gold/dim_date`
   - `gold/dim_well`
   - `gold/fact_production`
7. Lanzar una materialización/backfill para el rango mensual requerido, por
   ejemplo `2016-01-01...2016-03-01`.
8. Esperar el run y revisar los eventos:
   - `silver_dbt_assets` debe terminar exitosamente.
   - Los asset checks de `silver/silver_production` deben quedar verdes; el
     check de frescura puede aparecer como warning.
   - `gold_dbt_assets` debe ejecutarse después de Silver.

Si un check bloqueante falla, Dagster detiene la promoción: `gold_dbt_assets` no
corre y las tablas `gold` conservan el último valor válido.

## Procedimiento por CLI

Ejecutar desde `apps/data`.

1. Preparar dbt y las definiciones:

   ```bash
   export PYTHONPATH="$PWD/src"
   uv run dbt deps --project-dir dbt
   uv run dbt parse --project-dir dbt --profiles-dir dbt
   ```

2. Asegurar schemas medallion:

   ```bash
   uv run dagster asset materialize \
     --module-name petrocast_data.definitions \
     --select "warehouse_schemas_ready"
   ```

3. Refrescar Bronze desde las fuentes configuradas:

   ```bash
   uv run dagster asset materialize \
     --module-name petrocast_data.definitions \
     --select "dlt_petrocast_bronze_production_by_well,dlt_petrocast_bronze_wells_registry" \
     --partition 2026-05-01
   ```

4. Rematerializar Silver y Gold para el rango histórico:

   ```bash
   uv run dagster asset materialize \
     --module-name petrocast_data.definitions \
     --select "tag:silver,tag:gold" \
     --partition-range 2016-01-01...2016-03-01
   ```

Para un solo mes, usar `--partition 2016-01-01` en vez de `--partition-range`.

## Validación

1. En Dagster, el run de backfill debe terminar en verde.
2. En el asset `silver/silver_production`, los checks bloqueantes deben estar en
   verde. El check de frescura puede quedar en warning si los datos son
   históricos.
3. Confirmar que `gold.fact_production` tiene filas para el rango esperado:

   ```sql
   select
       production_month,
       count(*) as rows,
       sum(oil_prod_m3) as oil_prod_m3
   from gold.fact_production
   where production_month >= date '2016-01-01'
     and production_month < date '2016-04-01'
   group by production_month
   order by production_month;
   ```

4. Confirmar que el reproceso no generó duplicados:

   ```sql
   select well_id, production_month, count(*) as rows
   from gold.fact_production
   where production_month >= date '2016-01-01'
     and production_month < date '2016-04-01'
   group by well_id, production_month
   having count(*) > 1;
   ```

   La consulta debe devolver cero filas.

5. Guardar evidencia mínima: rango reprocesado, run id de Dagster, resultado de
   checks y conteos de `gold.fact_production`.

## Plan B y escalamiento

- Si falla la conexión al DW, revisar `PETROCAST_DW_*` y que el contenedor
  `data-postgres` esté sano.
- Si falla Bronze, revisar las URLs o reemplazarlas temporalmente por CSVs
  locales verificables en `.env`.
- Si fallan checks bloqueantes, no forzar Gold: revisar filas fallidas en
  `dbt_test__audit`, corregir la fuente o el mapeo, refrescar Bronze y repetir
  el rango.
- Si el rango es grande o el run compite con Metabase/DataHub, dividir el
  backfill en rangos más chicos y correrlo fuera de horario.
- Si el bloqueo impacta una demo o entrega, escalar al Data Owner con el run id,
  el rango afectado y las filas fallidas.

## Consideraciones no funcionales

- **Idempotencia:** Silver y Gold usan `delete+insert` por ventana mensual; repetir
  el mismo rango debe dejar el mismo resultado, sin duplicados.
- **Continuidad:** ante datos inválidos, Gold conserva el último snapshot válido.
- **Performance:** preferir ventanas chicas para backfills largos y evitar horas
  de uso interactivo de BI.
- **Trazabilidad:** cada backfill debe dejar evidencia reproducible en Dagster y
  en las consultas de validación.

## Referencias

- ADR-0023: arquitectura medallion y dbt.
- ADR-0025: calidad de datos y consecuencia operativa.
- ADR-0026: tipo de carga por capa.
- ADR-0028: Dagster y dlt.
- F2-23: procedimiento de backfill documentado y verificable.
