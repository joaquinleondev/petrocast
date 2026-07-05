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
- `petrocast_ml.features.schema` congela la proyección del feature store
  (contrato A) y las columnas de entrada del modelo (`MODEL_INPUT_COLUMNS`);
  `validate_feature_frame()` rechaza frames que violan la regla point-in-time.
- `build_training_dataset()`, `build_inference_frame()` y `as_model_input()`
  arman los frames consumibles por training (F3-13) e inferencia (F3-18) según
  el contrato F (horizonte `h` apunta a `as_of_date + (h - 1)` meses), sin
  recomputar features.
- `compute_well_features()` es el espejo pandas del modelo dbt
  `well_features` — la especificación ejecutable que usan los tests PIT; no es
  un camino de serving (el único escritor del store es dbt, ADR-0031).
- `train()` define el contrato del pipeline de entrenamiento de F3-13.
- `create_tracking_client()` define el cliente de runs de F3-14.
- `create_registry_client()` y `promote_champion()` definen el registry de F3-16.
- `load_champion()` y `predict()` definen el runtime de inferencia de F3-18.

Las implementaciones diferidas fallan explícitamente con `NotImplementedError`
hasta que aterrice el issue correspondiente; sus firmas quedan disponibles para
que API y Data integren el paquete sin duplicar contratos.

## Verificación

```bash
uv sync --frozen
uv run pytest
uv run ruff check .
uv run mypy
docker build -t petrocast-ml:dev .
```
