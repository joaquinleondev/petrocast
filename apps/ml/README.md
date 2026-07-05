# Petrocast ML

Paquete compartido para entrenamiento, tracking, registry e inferencia del modelo
predictivo de Petrocast. No incluye FastAPI, Dagster ni dbt: esas herramientas
permanecen en sus aplicaciones dueñas.

## Preparación local

```bash
cd apps/ml
cp .env.example .env
uv sync --frozen
```

La configuración sigue ADR-0018 y se lee desde variables de entorno o desde el
archivo `apps/ml/.env`. Los valores reales y credenciales no se versionan.

| Variable | Uso |
| --- | --- |
| `MLFLOW_TRACKING_URI` | Servidor de tracking y registry de MLflow |
| `MLFLOW_EXPERIMENT_NAME` | Experimento donde se registran los entrenamientos |
| `PETROCAST_MLFLOW_ARTIFACT_ROOT` | Ubicación de artefactos, local o S3 |
| `PETROCAST_MLFLOW_MODEL_NAME` | Modelo registrado, por defecto `petrocast-production` |
| `PETROCAST_MLFLOW_MODEL_ALIAS` | Alias servido, por defecto `champion` |

El URI estable del modelo servido es
`models:/petrocast-production@champion`.

## Interfaces públicas

- `read_features()` delega la lectura al feature store mediante `FeatureReader`.
- `train()` entrena el baseline LightGBM global (F3-13).
- `create_tracking_client()` y `record_training_run()` registran cada
  entrenamiento en MLflow (F3-14).
- `create_registry_client()` y `promote_champion()` definen el registry de F3-16.
- `load_champion()` y `predict()` definen el runtime de inferencia de F3-18.

Las implementaciones aún diferidas (registry de F3-16, inferencia de F3-18)
fallan explícitamente con `NotImplementedError` hasta que aterrice su issue; sus
firmas quedan disponibles para que API y Data integren el paquete sin duplicar
contratos.

## Entrenamiento local (F3-13)

Baseline reproducible según ADR-0030: **un único LightGBM global** sobre todos
los pozos, con las features del contrato A más `horizon` como input (estrategia
multi-step directa) y las estáticas de `dim_well` como categóricas nativas
(cold-start). Parámetros **fijos** en `training.FIXED_PARAMS` — sin tuning en
esta fase.

El split es **temporal, nunca aleatorio**: `as_of_date` del request es el corte
único de evaluación (test); los cortes anteriores van a train (y opcionalmente
validation con `--validation-cutoffs`). El target sigue el contrato F: horizonte
`h` apunta al mes `as_of + (h − 1)`; meses sin actual observado no generan fila.
La baseline naive (persistencia: último valor observado antes del corte) se
computa **sobre el mismo split** y sus MAE/RMSE en m³ acompañan las métricas del
modelo.

Entrenar offline contra los fixtures del repo (sin base de datos ni MLflow):

```bash
uv run python -m petrocast_ml.training \
  --features-csv tests/fixtures/well_features.csv \
  --production-csv tests/fixtures/production_monthly.csv \
  --as-of 2026-01-01 \
  --horizons 1,2,3 \
  --output-dir ./artifacts/baseline
```

El artefacto queda en `--output-dir`: `model.txt` (booster de LightGBM,
cargable sin sklearn vía `training.load_booster`) y `metadata.json` con request,
huella del dataset (filas, pozos, cortes, horizontes), parámetros, métricas y
versiones de código (`PETROCAST_GIT_SHA` se registra si está en el entorno).
Contra el warehouse real, el extract de features llega con la materialización
de F3-12; el tracking en MLflow con F3-14.

## Tracking de experimentos (F3-14)

Cada entrenamiento puede registrarse en MLflow con el flag `--track`. El
pipeline (`train()`) sigue **puro y determinístico**: el logging vive en
`tracking.py` y se dispara solo desde el CLI, así los smokes offline no
necesitan servidor. Requiere `MLFLOW_TRACKING_URI` apuntando al servidor
(contrato C); el SHA de código se toma de `PETROCAST_GIT_SHA`.

```bash
export MLFLOW_TRACKING_URI=http://localhost:5000
export PETROCAST_GIT_SHA=$(git rev-parse HEAD)
uv run python -m petrocast_ml.training \
  --features-csv tests/fixtures/well_features.csv \
  --production-csv tests/fixtures/production_monthly.csv \
  --as-of 2026-01-01 --horizons 1,2,3 \
  --output-dir ./artifacts/baseline --track
```

Cada run registra: **parámetros** (hiperparámetros efectivos de LightGBM +
horizonte y huella del dataset), **métricas** (`model_mae_m3`, `model_rmse_m3`,
`naive_mae_m3`, `naive_rmse_m3` y conteos de filas), los **tags obligatorios del
contrato C** (`as_of_date`, `features_version`, `git_commit`) y los **artefactos**
`model.txt` + `metadata.json`. El run se nombra `<as_of_date>-h<horizonte>`, de
modo que dos cortes aparecen como dos runs distinguibles.

Para la demo: abrir la UI de MLflow en `MLFLOW_TRACKING_URI`, entrar al
experimento `petrocast-production-forecast` y comparar runs filtrando por el tag
`as_of_date` (`tags.as_of_date = '2026-01-01'`).

## Verificación

```bash
uv sync --frozen
uv run pytest
uv run ruff check .
uv run mypy
docker build -t petrocast-ml:dev .
```
