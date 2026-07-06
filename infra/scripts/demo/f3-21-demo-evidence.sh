#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-http://localhost:5000}"
MLFLOW_EXPERIMENT_NAME="${MLFLOW_EXPERIMENT_NAME:-petrocast-production-forecast}"
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-abcdef12345}"
API_WELL_ID="${API_WELL_ID:-POZO-001}"
API_WELL_WITHOUT_FEATURES="${API_WELL_WITHOUT_FEATURES:-POZO-003}"
PARTITION="${PARTITION:-2026-01-01}"
DEMO_DIR="${DEMO_DIR:-${TMPDIR:-/tmp}/petrocast-f3-21-demo}"

usage() {
  cat <<'EOF'
Usage:
  infra/scripts/demo/f3-21-demo-evidence.sh <command>

Commands:
  tracking-runs   Create two MLflow training runs with different metrics.
  api-offline     Exercise prediction API scenarios through FastAPI TestClient.
  api-live        Exercise prediction API scenarios against a running API.
  retrain-cli     Trigger the Dagster retraining asset chain by partition.

Environment:
  MLFLOW_TRACKING_URI       default: http://localhost:5000
  MLFLOW_EXPERIMENT_NAME    default: petrocast-production-forecast
  API_BASE_URL              default: http://localhost:8000
  API_KEY                   default: abcdef12345
  API_WELL_ID               default: POZO-001
  API_WELL_WITHOUT_FEATURES default: POZO-003
  PARTITION                 default: 2026-01-01
  DEMO_DIR                  default: ${TMPDIR:-/tmp}/petrocast-f3-21-demo
EOF
}

run_training() {
  local run_name="$1"
  local horizons="$2"
  local features_version="$3"
  local output_dir="$DEMO_DIR/$run_name"
  local output
  local status

  rm -rf "$output_dir"
  echo
  echo "==> Creating MLflow run: $run_name (horizons=$horizons)"
  set +e
  output="$(
    cd "$ROOT_DIR/apps/ml" && \
      python -m uv run python -m petrocast_ml.training \
        --features-csv tests/fixtures/well_features.csv \
        --production-csv tests/fixtures/production_monthly.csv \
        --as-of 2026-01-01 \
        --horizons "$horizons" \
        --features-version "$features_version" \
        --output-dir "$output_dir" \
        --track
  )"
  status=$?
  set -e

  printf '%s\n' "$output"
  if ! grep -Eq '"tracked_run": "[^"]+"' <<<"$output"; then
    echo "ERROR: no tracked_run was produced. Is MLflow reachable at $MLFLOW_TRACKING_URI?" >&2
    return 1
  fi
  if [ "$status" -ne 0 ]; then
    echo "Note: quality gates failed, but the tracked run was created for demo evidence."
  fi
}

tracking_runs() {
  mkdir -p "$DEMO_DIR"
  export MLFLOW_TRACKING_URI
  export MLFLOW_EXPERIMENT_NAME
  export PETROCAST_GIT_SHA="${PETROCAST_GIT_SHA:-$(git -C "$ROOT_DIR" rev-parse --short HEAD)}"

  run_training "horizon-1" "1" "f3-21-demo-h1"
  run_training "horizon-1-2-3" "1,2,3" "f3-21-demo-h123"

  echo
  echo "Open $MLFLOW_TRACKING_URI and compare the two runs in experiment '$MLFLOW_EXPERIMENT_NAME'."
}

api_offline() {
  echo "==> Running offline API scenarios through FastAPI TestClient"
  cd "$ROOT_DIR/apps/api"
  python -m uv run pytest tests/integration/api/v1/test_prediction.py -q
}

api_request() {
  local label="$1"
  local path="$2"

  echo
  echo "==> $label"
  echo "GET $API_BASE_URL$path"
  curl -sS -H "X-API-Key: $API_KEY" "$API_BASE_URL$path" \
    -w '\nHTTP_STATUS=%{http_code}\n'
}

api_live() {
  echo "==> Checking API liveness at $API_BASE_URL"
  curl -sS "$API_BASE_URL/health/live" -w '\nHTTP_STATUS=%{http_code}\n'

  api_request \
    "Happy path: known well, three-month horizon" \
    "/api/v1/predictions?id_well=$API_WELL_ID&as_of_date=2024-03-15&horizon=3"
  api_request \
    "Boundary path: prediction months cross year boundary" \
    "/api/v1/predictions?id_well=$API_WELL_ID&as_of_date=2024-12-31&horizon=2"
  api_request \
    "Business error: well without persisted features" \
    "/api/v1/predictions?id_well=$API_WELL_WITHOUT_FEATURES&as_of_date=2024-03-15&horizon=3"
  api_request \
    "Validation error: horizon outside contract" \
    "/api/v1/predictions?id_well=$API_WELL_ID&as_of_date=2024-03-15&horizon=13"
}

retrain_cli() {
  echo "==> Triggering retraining_job asset chain for partition $PARTITION"
  cd "$ROOT_DIR/apps/data"
  python -m uv run dagster asset materialize \
    --module-name petrocast_data.definitions \
    --select "features/well_features,ml/training_candidate,ml/model_evaluation,ml/champion_promotion" \
    --partition "$PARTITION"
}

case "${1:-}" in
  tracking-runs)
    tracking_runs
    ;;
  api-offline)
    api_offline
    ;;
  api-live)
    api_live
    ;;
  retrain-cli)
    retrain_cli
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
