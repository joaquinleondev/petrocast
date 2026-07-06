# Petrocast API

FastAPI service that exposes well listings and production forecasts from the
gold schema of the Petrocast data warehouse.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/wells` | required | List all wells |
| GET | `/api/v1/forecast` | required | Production history for a well |
| GET | `/api/v1/predictions` | required | Monthly oil production predictions for a well |
| GET | `/health/live` | none | Liveness probe |
| GET | `/health/ready` | none | Readiness probe |
| GET | `/health/deep` | required | Full health check |

Authentication: pass `X-API-Key: <key>` header. Missing or invalid key returns **403**.

### Predictions (contrato D — ADR-0034, Fase 3)

Request: `id_well` (the `well_id` key of `gold.fact_production`), `as_of_date`
(cutoff date) and `horizon` in months (1-12). Response: one prediction per
month starting after `as_of_date`, in m³, plus traceability metadata
(`model_version`, `as_of_date`, `horizon`). Errors: `404` (unknown well / no
history at `as_of_date`), `422` (validation), `503` (model or feature store
unavailable), `403` (auth).

```bash
curl -H "X-API-Key: abcdef12345" \
  "http://localhost:8000/api/v1/predictions?id_well=POZO-001&as_of_date=2024-03-15&horizon=3"
```

Expected response (`200`):

```json
{
  "id_well": "POZO-001",
  "as_of_date": "2024-03-15",
  "horizon": 3,
  "model_version": "7",
  "predictions": [
    { "month": "2024-04-01", "oil_prod_m3": 1234.5 },
    { "month": "2024-05-01", "oil_prod_m3": 1180.2 },
    { "month": "2024-06-01", "oil_prod_m3": 1125.9 }
  ]
}
```

> The endpoint serves the **registry champion** (F3-18): the loader resolves
> `models:/petrocast-production@champion` (F3-16) and runs it over the persisted
> point-in-time features (`features.well_features`, contract A). `as_of_date` is
> the cutoff (last observed month); the model reads features at `as_of_date + 1`
> (its first-unknown-month convention) and horizon step `s` predicts month
> `as_of_date + s`. `model_version` reports the concrete champion version that
> answered. `503` means the MLflow registry (model) or the warehouse is
> unavailable — the endpoint degrades gracefully and retries on the next call.

## Configuration

All settings are read from environment variables (or `.env`). See `.env.example` for the
full list.

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | `abcdef12345` | API key for protected endpoints |
| `PETROCAST_DW_HOST` | `localhost` | Postgres host |
| `PETROCAST_DW_PORT` | `5432` | Postgres port |
| `PETROCAST_DW_USER` | `petrocast` | Postgres user |
| `PETROCAST_DW_PASSWORD` | `petrocast` | Postgres password |
| `PETROCAST_DW_DATABASE` | `petrocast` | Postgres database |
| `PETROCAST_MLFLOW_TRACKING_URI` | `http://localhost:5000` | MLflow tracking/registry server the champion loads from |
| `PETROCAST_MLFLOW_MODEL_NAME` | `petrocast-production` | Registered model name |
| `PETROCAST_MLFLOW_MODEL_ALIAS` | `champion` | Alias resolved to the serving version |

The API reads from the `gold` and `features` schemas:

- `gold.dim_well` — well metadata
- `gold.fact_production` — monthly production actuals (oil_prod_m3)
- `features.well_features` — persisted point-in-time features (contract A), read
  by `(well_id, as_of_date)` for inference

**The data stack must be running** (see `infra/compose.data.yml`) before starting
the API with `infra/compose.dev.yml`.

## Development

```bash
cd apps/api
uv sync
uv run fastapi dev src/main.py
```

## Testing

```bash
cd apps/api
uv run pytest -q          # all tests, coverage report
uv run ruff check .       # lint
uv run mypy src           # type checks
```

Tests run fully offline — no Postgres required. The DB dependency is overridden
in `tests/conftest.py` with a fake connection returning canned gold-schema rows.
