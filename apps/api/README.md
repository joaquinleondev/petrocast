# Petrocast API

FastAPI service that exposes well listings and production forecasts from the
gold schema of the Petrocast data warehouse.

## Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/wells` | required | List all wells |
| GET | `/api/v1/forecast` | required | Production history for a well |
| GET | `/health/live` | none | Liveness probe |
| GET | `/health/ready` | none | Readiness probe |
| GET | `/health/deep` | required | Full health check |

Authentication: pass `X-API-Key: <key>` header. Missing or invalid key returns **403**.

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

The API reads from the `gold` schema:

- `gold.dim_well` — well metadata
- `gold.fact_production` — monthly production actuals (oil_prod_m3)

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
