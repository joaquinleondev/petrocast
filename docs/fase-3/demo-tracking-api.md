# Evidencia demo de tracking, API y retraining

Guía de evidencia para F3-21. El objetivo es grabar o repetir una demo local que
muestre:

- dos runs de entrenamiento en MLflow con métricas distintas;
- llamadas a la API de predicciones bajo escenarios distintos;
- trigger manual del job de retraining en Dagster;
- capturas concretas para el video final.

No requiere producción live. Todo se puede ejecutar con servicios locales o con
los tests offline del repo.

## Preparación local

Desde la raíz del repo:

```bash
cp apps/data/.env.example apps/data/.env
docker compose --env-file apps/data/.env \
  -f infra/compose.data.yml \
  -f infra/compose.mlflow.yml \
  up --build data-postgres mlflow dagster
```

Servicios esperados:

- Dagster: <http://localhost:3000>
- MLflow: <http://localhost:5000>
- PostgreSQL local del stack de datos: `data-postgres`

El helper de esta guía vive en:

```bash
infra/scripts/demo/f3-21-demo-evidence.sh
infra/scripts/demo/f3-21-demo-evidence.ps1
```

## 1. Runs de tracking con métricas distintas

Con MLflow levantado:

```bash
# PowerShell
.\infra\scripts\demo\f3-21-demo-evidence.ps1 tracking-runs

# Bash
MLFLOW_TRACKING_URI=http://localhost:5000 \
  infra/scripts/demo/f3-21-demo-evidence.sh tracking-runs
```

El script entrena dos veces contra los fixtures de `apps/ml/tests/fixtures`:

| Run | Corte | Horizontes | Resultado esperado |
| --- | --- | --- | --- |
| `horizon-1` | `2026-01-01` | `1` | Run registrado con MAE/RMSE del modelo y naive baseline |
| `horizon-1-2-3` | `2026-01-01` | `1,2,3` | Run registrado con métricas distintas al primer run |

Resultados esperados con los fixtures actuales:

- `horizon-1`: `model_mae_m3` cercano a `216.25`, `test_rows=4`.
- `horizon-1-2-3`: `model_mae_m3` cercano a `214.18`, `test_rows=11`.
- Los gates pueden quedar en rojo (`gates_passed=false`) porque estos datos son
  mínimos de demo. Eso no invalida la evidencia de tracking: los runs, métricas,
  tags y artefactos quedan registrados en MLflow.

Evidencia para capturar en MLflow:

- experimento `petrocast-production-forecast` con al menos dos runs;
- columnas/tags `as_of_date`, `features_version`, `git_commit`;
- métricas `model_mae_m3`, `model_rmse_m3`, `naive_mae_m3`, `naive_rmse_m3`;
- artefactos `model.txt`, `metadata.json` y `evaluation.json`.

## 2. API de predicciones

### Opción offline

Esta opción no levanta API, Postgres ni MLflow. Ejecuta requests reales contra
FastAPI usando `TestClient` y fakes versionados del repo:

```bash
# PowerShell
.\infra\scripts\demo\f3-21-demo-evidence.ps1 api-offline

# Bash
infra/scripts/demo/f3-21-demo-evidence.sh api-offline
```

Escenarios cubiertos:

| Escenario | Request | Resultado esperado |
| --- | --- | --- |
| Happy path | `POZO-001`, `2024-03-15`, horizonte `3` | `200`, tres meses predichos |
| Cruce de año | `POZO-001`, `2024-12-31`, horizonte `2` | `200`, meses `2025-01-01` y `2025-02-01` |
| Pozo sin features | `POZO-003`, `2024-03-15`, horizonte `3` | `404`, mensaje `no persisted features` |
| Horizonte inválido | horizonte `13` | `422` |
| API key faltante | sin header `X-API-Key` | `403` |
| Modelo o warehouse caído | dependencias forzadas a fallar | `503` |

### Opción con API local

Con el stack de datos ya levantado, levantar la API en otra terminal desde el
host. Esta forma evita problemas de red entre contenedores, porque la API puede
resolver PostgreSQL y MLflow por `localhost`:

```bash
cd apps/api
uv sync --frozen
uv run fastapi dev src/main.py
```

Luego ejecutar:

```bash
# PowerShell
.\infra\scripts\demo\f3-21-demo-evidence.ps1 api-live

# Bash
API_BASE_URL=http://localhost:8000 \
API_KEY=abcdef12345 \
  infra/scripts/demo/f3-21-demo-evidence.sh api-live
```

Los valores por defecto `POZO-001` y `POZO-003` coinciden con los fixtures
offline de los tests. Si se usa un warehouse real local, primero elegir un pozo
existente con `GET /api/v1/wells` y pasar:

```bash
# PowerShell
.\infra\scripts\demo\f3-21-demo-evidence.ps1 api-live `
  -ApiWellId <well_id_real> `
  -ApiWellWithoutFeatures <well_id_sin_features_o_inexistente>

# Bash
API_WELL_ID=<well_id_real> \
API_WELL_WITHOUT_FEATURES=<well_id_sin_features_o_inexistente> \
  infra/scripts/demo/f3-21-demo-evidence.sh api-live
```

Si se prefiere correr la API en Docker, la variable
`PETROCAST_MLFLOW_TRACKING_URI` debe apuntar a `http://mlflow:5000` dentro de la
red de Compose, no a `localhost`.

Requests equivalentes para pegar manualmente:

```bash
curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=POZO-001&as_of_date=2024-03-15&horizon=3"

curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=POZO-001&as_of_date=2024-12-31&horizon=2"

curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=POZO-003&as_of_date=2024-03-15&horizon=3"

curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=POZO-001&as_of_date=2024-03-15&horizon=13"
```

Evidencia para capturar:

- terminal con respuesta `200` y `model_version`;
- terminal con respuesta `404` para pozo sin features;
- terminal con respuesta `422` para validación;
- si se muestra Swagger/OpenAPI, endpoint `GET /api/v1/predictions`.

## 3. Trigger manual de retraining

Con PostgreSQL, Dagster y MLflow levantados:

```bash
# PowerShell
.\infra\scripts\demo\f3-21-demo-evidence.ps1 retrain-cli -Partition 2026-01-01

# Bash
PARTITION=2026-01-01 \
  infra/scripts/demo/f3-21-demo-evidence.sh retrain-cli
```

El comando materializa la cadena:

```text
features/well_features
ml/training_candidate
ml/model_evaluation
ml/champion_promotion
```

También se puede demostrar desde la UI:

1. Abrir <http://localhost:3000>.
2. Ir a **Jobs**.
3. Abrir `retraining_job`.
4. Elegir una partición mensual, por ejemplo `2026-01-01`.
5. Lanzar el run.

Evidencia para capturar en Dagster:

- `retraining_job` visible en Jobs;
- partición mensual elegida;
- run lanzado manualmente;
- assets materializados o step fallido por gates;
- metadata `as_of_date`, `mlflow_run_id`, métricas y `promotion_status`.

Si los gates fallan, el comportamiento esperado es seguro: el candidato queda
trazado en MLflow, pero `ml/champion_promotion` bloquea la promoción y no mueve
el alias `champion`.

## Checklist para el video

- [ ] MLflow UI con dos runs y métricas diferentes.
- [ ] Detalle de un run mostrando params, métricas, tags y artefactos.
- [ ] API respondiendo una predicción exitosa.
- [ ] API mostrando un error controlado (`404` o `422`).
- [ ] Dagster UI o CLI mostrando trigger manual de `retraining_job`.
- [ ] Explicación corta: el modelo servido usa `models:/petrocast-production@champion`.
- [ ] Explicación corta: un retrain fallido no pisa el champion vigente.

## Limpieza

```bash
docker compose --env-file apps/data/.env \
  -f infra/compose.data.yml \
  -f infra/compose.mlflow.yml \
  down
```

Si se usó el helper, sus artefactos quedan fuera del repo por defecto:

```bash
rm -rf "${TMPDIR:-/tmp}/petrocast-f3-21-demo"
```
