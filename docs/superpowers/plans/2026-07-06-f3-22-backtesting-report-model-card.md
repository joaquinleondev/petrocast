# F3-22 Backtesting Report + Model Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Producir `docs/fase-3/model-card.md` y `docs/fase-3/backtesting-report.md` con números reales de una corrida end-to-end (datos.gob.ar → feature store → assets Dagster de retraining → MLflow champion), cerrando el issue #125.

**Architecture:** Infraestructura local efímera (postgres + MLflow sqlite) alimenta la cadena de assets mergeada en F3-19 (`ml/training_candidate` → `ml/model_evaluation` → `ml/champion_promotion`). El `evaluation.json` y los metadatos MLflow de esa corrida son la única fuente de números de ambos documentos. Nada de la infraestructura entra al repo; solo los dos docs, el anexo JSON y el spec/plan.

**Tech Stack:** docker (postgres:16), uv, Dagster, dbt, dlt, MLflow 3.x (backend sqlite), markdownlint-cli2.

## Global Constraints

- Docs en español, mismo estilo que `docs/` existente.
- Convenciones congeladas: contrato F (single-origin, horizontes 1–3, target `as_of + (h − 1)`); MASE denominador = diffs entre filas observadas sucesivas; elegibilidad ≥ 12 meses observados antes del cutoff.
- Gates ADR-0030: `mase_median` < 1.0 (bloqueante), `mae_vs_naive` ratio ≤ 1.0 (bloqueante), `mape_vs_arps` margen ≤ 2.0 pp (informativo).
- MLflow 3.14 rechaza file store → backend `sqlite:///`.
- dbt gold con `--indirect-selection cautious` (gotcha conocido de selección eager).
- Branch: `docs/f3-22-model-card-backtesting`. PR: `docs(ml): add model card and backtesting report`, `Closes #125`.
- Scratchpad para todo lo temporal: `$SCRATCH` = `/private/tmp/claude-501/-Users-ignacio-petrocast/ba20538a-27bd-460b-a3de-c83c30c6c9bf/scratchpad`.

---

### Task 1: Dimensionar el recurso real y elegir ventana/cutoff

**Files:**

- Create: `$SCRATCH/f3-22/resources.json` (inventario de recursos del dataset)

**Interfaces:**

- Produces: variables de la corrida — `PROD_URL` (URL CSV de producción), `WELLS_URL` (registro de pozos), `CUTOFF` (as_of del backtest, primer día de mes), `FEATURE_MONTHS` (lista de particiones as_of a materializar).

- [ ] **Step 1: Inventariar recursos del dataset capítulo IV**

```bash
mkdir -p $SCRATCH/f3-22
curl -sS -H "User-Agent: petrocast-data/0.1" \
  "https://datos.gob.ar/api/3/action/package_show?id=energia-produccion-petroleo-gas-por-pozo-capitulo-iv" \
  | python3 -c "
import json,sys
d=json.load(sys.stdin)['result']['resources']
out=[{'id':r['id'],'name':r.get('name'),'url':r.get('url'),'size':r.get('size'),'format':r.get('format')} for r in d]
json.dump(out,open('$SCRATCH/f3-22/resources.json','w'),indent=2,ensure_ascii=False)
print(json.dumps(out,indent=2,ensure_ascii=False)[:3000])
"
```

Expected: lista de recursos con URLs y tamaños; identificar el recurso de producción por pozo que referencia `apps/data/.env.example` (`b5b58cdc-...`) y el de pozos (`cbfa4d79-...`).

- [ ] **Step 2: Medir tamaño real de los CSVs (HEAD, sin descargar)**

```bash
curl -sSI -H "User-Agent: petrocast-data/0.1" "<PROD_CSV_URL>" | grep -i -E "content-length|location"
```

Regla de decisión:

- ≤ ~2 GB y ventana ≥ 24 meses → usar ese recurso completo.
- Recurso inviable (muy grande o sin historia suficiente) → elegir en `resources.json` el recurso alternativo más chico que cubra ≥ 24 meses contiguos (los datasets de capítulo IV suelen venir particionados por período) y usar su URL como `PETROCAST_SOURCE_PRODUCTION_URL`. El alcance elegido se declara en el reporte.

- [ ] **Step 3: Fijar cutoff y particiones de features**

Regla: `CUTOFF = (último mes con datos) − 2 meses` (los horizontes 1–3 necesitan actuals hasta `as_of + 2`). `FEATURE_MONTHS` = 24 meses terminando en `CUTOFF`. Anotar ambos en `$SCRATCH/f3-22/run-params.env` como `export PROD_URL=... WELLS_URL=... CUTOFF=... FEATURE_MONTHS="..."`.

- [ ] **Step 4: Commit del avance del plan** — no aplica (nada del repo cambió). Continuar.

### Task 2: Infraestructura local efímera (postgres + MLflow)

**Files:**

- Create: `$SCRATCH/f3-22/mlflow/` (backend sqlite + artifacts, fuera del repo)

**Interfaces:**

- Produces: postgres en `localhost:5432` (user/pass/db `petrocast`), MLflow en `http://localhost:5000`.

- [ ] **Step 1: Postgres efímero con init scripts**

```bash
docker run -d --name f3-22-pg \
  -e POSTGRES_USER=petrocast -e POSTGRES_PASSWORD=petrocast -e POSTGRES_DB=petrocast \
  -p 5432:5432 \
  -v /Users/ignacio/petrocast/infra/data/postgres/init:/docker-entrypoint-initdb.d:ro \
  postgres:16
until docker exec f3-22-pg pg_isready -U petrocast -d petrocast; do sleep 1; done
```

Expected: `accepting connections`.

- [ ] **Step 2: MLflow server local (sqlite backend)**

```bash
mkdir -p $SCRATCH/f3-22/mlflow
cd /Users/ignacio/petrocast/apps/ml && uv run mlflow server \
  --backend-store-uri sqlite:///$SCRATCH/f3-22/mlflow/mlflow.db \
  --default-artifact-root $SCRATCH/f3-22/mlflow/artifacts \
  --host 127.0.0.1 --port 5000 &
sleep 5 && curl -sS http://127.0.0.1:5000/health
```

Expected: `OK`.

- [ ] **Step 3: Env vars de la corrida**

```bash
cd /Users/ignacio/petrocast/apps/data
export PYTHONPATH=$PWD/src \
  PETROCAST_SOURCE_PRODUCTION_URL="$PROD_URL" \
  PETROCAST_SOURCE_WELLS_URL="$WELLS_URL" \
  PETROCAST_DW_HOST=localhost PETROCAST_DW_PORT=5432 \
  PETROCAST_DW_USER=petrocast PETROCAST_DW_PASSWORD=petrocast \
  PETROCAST_DW_DATABASE=petrocast \
  DBT_PROFILES_DIR=$PWD/dbt \
  PETROCAST_MLFLOW_TRACKING_URI=http://127.0.0.1:5000 \
  PETROCAST_ML_ARTIFACT_DIR=$SCRATCH/f3-22/ml-artifacts \
  PETROCAST_GIT_SHA=$(git -C /Users/ignacio/petrocast rev-parse --short HEAD)
```

### Task 3: Ingesta bronze real + dbt silver/gold

**Interfaces:**

- Consumes: postgres y env vars de Task 2.
- Produces: `gold.fact_production` poblada con la ventana real.

- [ ] **Step 1: Schemas + bronze (particiones reales)**

```bash
cd /Users/ignacio/petrocast/apps/data
uv run dagster asset materialize -m petrocast_data.definitions \
  --select "warehouse_schemas_ready" 2>&1 | tail -2
uv run dagster asset materialize -m petrocast_data.definitions \
  --select "bronze/production_by_well,bronze/wells_registry" \
  --partition "<ÚLTIMO_MES>" 2>&1 | tail -3
```

Expected: `RUN_SUCCESS`. Nota: una partición = snapshot completo del recurso (el CSV trae toda la historia); si la descarga falla por timeout, reintentar una vez y si persiste documentar y bajar a un recurso más chico (regla de Task 1).

- [ ] **Step 2: Verificar volumen en bronze**

```bash
docker exec f3-22-pg psql -U petrocast -d petrocast -c \
  "select count(*) filas, min(fecha_data) desde, max(fecha_data) hasta from bronze.production_by_well;"
```

Expected: filas > 0 y ventana ≥ 24 meses. (Si el nombre de columna de fecha difiere, listar columnas con `\d bronze.production_by_well` y ajustar.)

- [ ] **Step 3: dbt silver + gold**

```bash
cd /Users/ignacio/petrocast/apps/data
uv run dbt build --project-dir dbt --select tag:silver 2>&1 | tail -3
uv run dbt build --project-dir dbt --select tag:gold --indirect-selection cautious 2>&1 | tail -3
docker exec f3-22-pg psql -U petrocast -d petrocast -c \
  "select count(*) filas, count(distinct well_id) pozos, min(production_month), max(production_month) from gold.fact_production;"
```

Expected: builds `PASS`, `gold.fact_production` con pozos > 100 y ventana completa.

### Task 4: Feature store — 24 particiones as_of

**Interfaces:**

- Consumes: `gold.fact_production`.
- Produces: `features.well_features` con snapshots para cada mes de `FEATURE_MONTHS`.

- [ ] **Step 1: Loop de materialización por cutoff**

```bash
cd /Users/ignacio/petrocast/apps/data
for m in $FEATURE_MONTHS; do
  uv run dbt build --project-dir dbt --select tag:features \
    --vars "{\"as_of_date\": \"$m\"}" --indirect-selection cautious 2>&1 | tail -1
done
```

Expected: cada build `PASS` (incluye el test PIT singular).

- [ ] **Step 2: Verificar snapshots**

```bash
docker exec f3-22-pg psql -U petrocast -d petrocast -c \
  "select as_of_date, count(*) pozos from features.well_features group by 1 order by 1;"
```

Expected: 24 filas de as_of_date, conteos de pozos estables.

### Task 5: Corrida ML end-to-end (training → evaluation → promotion)

**Interfaces:**

- Consumes: feature store, MLflow server, env vars.
- Produces: `$SCRATCH/f3-22/evaluation.json` (copia), `RUN_ID` MLflow, versión + alias del champion.

- [ ] **Step 1: Materializar la cadena ML en la partición del cutoff**

```bash
cd /Users/ignacio/petrocast/apps/data
uv run dagster asset materialize -m petrocast_data.definitions \
  --select "ml/training_candidate,ml/model_evaluation,ml/champion_promotion" \
  --partition "$CUTOFF" 2>&1 | tee $SCRATCH/f3-22/ml-run.log | tail -15
```

Expected: `RUN_SUCCESS` con metadata `promotion_status: promoted`, `mlflow_run_id`, `model_version`. Si un gate bloqueante falla (`CandidateNotApprovedError`), la corrida es igualmente material del reporte: documentar el veredicto real, no maquillarlo — y el criterio champion se cubre con el run del candidato + mecánica de promoción (decidir en el momento y dejarlo explícito en el reporte).

- [ ] **Step 2: Capturar evaluation.json y datos del run**

```bash
find $SCRATCH/f3-22/ml-artifacts -name evaluation.json -exec cp {} $SCRATCH/f3-22/evaluation.json \;
python3 -m json.tool $SCRATCH/f3-22/evaluation.json | head -40
grep -E "mlflow_run_id|model_version|alias" $SCRATCH/f3-22/ml-run.log
```

Expected: JSON con `gates`, `distributions`, conteos; run_id y versión anotados en `$SCRATCH/f3-22/run-params.env`.

- [ ] **Step 3: Verificar champion resuelto por alias**

```bash
cd /Users/ignacio/petrocast/apps/ml
PETROCAST_MLFLOW_TRACKING_URI=http://127.0.0.1:5000 uv run python -c "
from petrocast_ml import create_registry_client
from petrocast_ml.config import get_settings
s = get_settings()
v = create_registry_client(s).get_by_alias(name=s.mlflow_model_name, alias=s.mlflow_model_alias)
print(v)
"
```

Expected: `ModelVersion(name='petrocast-production', version=..., run_id=...)` — run_id igual al del Step 2. (Si `mlflow_tracking_uri` no toma la env var sin prefijo, exportar también `MLFLOW_TRACKING_URI`.)

### Task 6: `docs/fase-3/backtesting-report.md` + anexo

**Files:**

- Create: `docs/fase-3/backtesting-report.md`
- Create: `docs/fase-3/assets/evaluation-<CUTOFF>.json` (copia del evaluation.json)

**Interfaces:**

- Consumes: `$SCRATCH/f3-22/evaluation.json`, run_id/versión de Task 5.
- Produces: reporte con secciones: Resumen ejecutivo · Metodología · Cobertura · Gates · Resultados vs naive · Resultados vs Arps · Distribuciones per-well · Cómo reproducir · Anexo.

- [ ] **Step 1: Copiar anexo**

```bash
mkdir -p /Users/ignacio/petrocast/docs/fase-3/assets
cp $SCRATCH/f3-22/evaluation.json /Users/ignacio/petrocast/docs/fase-3/assets/evaluation-$CUTOFF.json
```

- [ ] **Step 2: Escribir el reporte**

Estructura obligatoria (números transcriptos del JSON, nunca inventados):

```markdown
# Reporte de backtesting — <CUTOFF>

## Resumen ejecutivo
(veredicto de gates + una frase por gate, en lenguaje de negocio)

## Metodología
(contrato F: split single-origin en as_of=<CUTOFF>, horizontes 1–3, target
as_of+(h−1); elegibilidad ≥12 meses; convención MASE; fuente de datos y
ventana ingerida; link al ADR-0030)

## Cobertura
| Métrica | Valor |  ← wells_in_test / wells_eligible /
                         wells_excluded_short_history / wells_mase_undefined

## Gates de calidad (ADR-0030)
| Gate | Umbral | Valor | Veredicto | Bloqueante |  ← gates[]

## Modelo vs naive (m³)
(model_mae_m3, naive_mae_m3, ratio; lectura en castellano)

## Modelo vs Arps
(arps_fitted_wells / arps_failed_wells / arps_degraded; gap de MAPE si aplica)

## Distribuciones per-well
(una tabla por métrica en distributions: mase, model_mae_m3, naive_mae_m3,
mape_nonzero_pct, arps_mape_nonzero_pct — cuantiles tal cual el JSON)

## Cómo reproducir
(comandos de Tasks 2–5, con las URLs/fechas usadas)

## Anexo
(link a assets/evaluation-<CUTOFF>.json y al run MLflow: run_id, experimento)
```

- [ ] **Step 3: Lint + commit**

```bash
cd /Users/ignacio/petrocast
npx markdownlint-cli2 "docs/fase-3/**/*.md"
git add docs/fase-3/backtesting-report.md docs/fase-3/assets/
git commit -m "docs(ml): backtesting report over real capitulo IV data [F3-22]"
```

Expected: `0 error(s)`.

### Task 7: `docs/fase-3/model-card.md`

**Files:**

- Create: `docs/fase-3/model-card.md`

**Interfaces:**

- Consumes: run_id/versión/alias de Task 5, reporte de Task 6.

- [ ] **Step 1: Escribir la model card**

Estructura obligatoria:

```markdown
# Model card — petrocast-production

## Detalles del modelo
(LightGBM baseline F3-13, hiperparámetros fijos, versión registrada,
alias champion, run_id MLflow, commit)

## Objetivo y uso previsto
(pronóstico mensual de producción de petróleo por pozo, horizontes 1–3,
consumidores: API de serving / video; usos fuera de alcance: gas/agua,
pozos sin 12 meses de historia, decisiones regulatorias)

## Datos
(datos.gob.ar capítulo IV, ventana ingerida, granularidad pozo-mes, m³)

## Features (contrato A, ADR-0031)
(familias: lags 1/2/3/6/12, rolling mean/std, trend, recencia,
intermitencia, categóricas cuenca/yacimiento/tipo de recurso)

## Métricas y evaluación
(resumen de gates + link al backtesting-report.md)

## Limitaciones y riesgos
### Leakage (mitigación: PIT test F3-11)
### Datos faltantes e intermitencia
### Drift (mitigación: retraining F3-19)
### Sesgos de cobertura

## Champion y trazabilidad
(cómo resolver models:/petrocast-production@champion, ADR-0032;
run de tracking vinculado)
```

- [ ] **Step 2: Lint + commit**

```bash
cd /Users/ignacio/petrocast
npx markdownlint-cli2 "docs/fase-3/**/*.md"
git add docs/fase-3/model-card.md
git commit -m "docs(ml): model card for the champion baseline [F3-22]"
```

### Task 8: Verificación final, limpieza y PR

- [ ] **Step 1: Cotejo de números**

Releer ambos docs contra `docs/fase-3/assets/evaluation-<CUTOFF>.json` campo por campo (gates, cuantiles, conteos). Cualquier divergencia se corrige antes del PR.

- [ ] **Step 2: Criterios de aceptación del issue**

Verificar los 5 checkboxes de #125 contra los docs. El criterio champion exige run_id + versión reales en la model card.

- [ ] **Step 3: Limpieza de infra**

```bash
docker rm -f f3-22-pg
kill %1 2>/dev/null  # mlflow server
```

- [ ] **Step 4: Push + PR**

```bash
cd /Users/ignacio/petrocast
git push -u origin docs/f3-22-model-card-backtesting
gh pr create --title "docs(ml): add model card and backtesting report" \
  --body "$(cat <<'EOF'
Closes #125

Model card y reporte de backtesting sobre datos reales de capítulo IV
(datos.gob.ar), generados con la cadena Dagster de F3-19 y MLflow local.
Incluye anexo evaluation.json para auditar los números sin MLflow.
EOF
)"
```

- [ ] **Step 5: Monitorear CI del PR en background y reportar veredicto.**

```bash
gh pr checks --watch
```
