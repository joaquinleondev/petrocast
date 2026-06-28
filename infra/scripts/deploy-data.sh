#!/usr/bin/env bash
# deploy-data.sh — bring up (and optionally seed) the Phase-2 data stack on the
# staging EC2 node. Materializes secrets from SSM Parameter Store, writes the
# compose env + the Traefik basic-auth middleware, and runs `docker compose up`.
#
# Invoked by bootstrap-swarm.sh at first boot, and re-runnable standalone via
# SSM Run Command (e.g. after pushing a new image, or to seed demo data):
#   bash /opt/petrocast/deploy-data.sh up      # default: (re)deploy the stack
#   bash /opt/petrocast/deploy-data.sh seed    # materialize a demo month range
#
# Config (region, ECR registry, domain, SSM path, compose dir) is read from
# /etc/petrocast/deploy-data.conf, written by the bootstrap.
set -euo pipefail
exec > >(tee -a /var/log/petrocast-deploy-data.log) 2>&1
echo "[$(date -u)] deploy-data.sh action=${1:-up}"

ACTION="${1:-up}"
CONF="/etc/petrocast/deploy-data.conf"
[ -f "$CONF" ] || { echo "ERROR: missing $CONF (run from a provisioned node)"; exit 1; }
# shellcheck disable=SC1090
. "$CONF" # provides: AWS_REGION ECR_REGISTRY DOMAIN ENV SSM_PATH COMPOSE_DIR

# Which slice of the data stack to run on the cloud node:
#   core (default) — only what the public API needs: warehouse + API. The
#                    orchestration/catalog/BI (Dagster, DataHub, Metabase) run
#                    locally on dev machines, so staging stays on a small box.
#   full           — also bring up Dagster + Metabase + DataHub (heavy; needs a
#                    bigger instance, e.g. t3.xlarge). Required for cloud `seed`.
DATA_STACK_PROFILE="${DATA_STACK_PROFILE:-core}"

ENV_DIR="/var/lib/petrocast"
DYNAMIC_DIR="/opt/petrocast/traefik-dynamic"
mkdir -p "$ENV_DIR" "$DYNAMIC_DIR"

COMPOSE_FILES=(
  -f "$COMPOSE_DIR/compose.data.yml"
  -f "$COMPOSE_DIR/compose.datahub.yml"
  -f "$COMPOSE_DIR/compose.dev.yml"
  -f "$COMPOSE_DIR/compose.staging.yml"
)
dc() { docker compose -p petrocast "${COMPOSE_FILES[@]}" --env-file "$ENV_DIR/stack.env" "$@"; }

# ── Secrets from SSM Parameter Store ─────────────────────────────────────────
get_param() {
  aws ssm get-parameter --region "$AWS_REGION" --with-decryption \
    --name "$SSM_PATH/$1" --query 'Parameter.Value' --output text
}
get_param_opt() {
  aws ssm get-parameter --region "$AWS_REGION" --with-decryption \
    --name "$SSM_PATH/$1" --query 'Parameter.Value' --output text 2>/dev/null || echo ""
}

echo "[deploy-data] reading secrets from SSM path $SSM_PATH"
DW_USER="$(get_param dw_user)"
DW_PASSWORD="$(get_param dw_password)"
DW_DATABASE="$(get_param dw_database)"
SOURCE_PRODUCTION_URL="$(get_param source_production_url)"
SOURCE_WELLS_URL="$(get_param source_wells_url)"
BI_DB_PASSWORD="$(get_param bi_db_password)"
NOTIFICATION_WEBHOOK_URL="$(get_param_opt notification_webhook_url)"
BASIC_AUTH_HTPASSWD="$(get_param basic_auth_htpasswd)"

# ── Compose env file (root-only) ─────────────────────────────────────────────
umask 077
cat > "$ENV_DIR/stack.env" <<EOF
PETROCAST_ECR_REGISTRY=$ECR_REGISTRY
PETROCAST_DOMAIN=$DOMAIN
PETROCAST_DW_USER=$DW_USER
PETROCAST_DW_PASSWORD=$DW_PASSWORD
PETROCAST_DW_DATABASE=$DW_DATABASE
PETROCAST_BI_DB_PASSWORD=$BI_DB_PASSWORD
PETROCAST_SOURCE_PRODUCTION_URL=$SOURCE_PRODUCTION_URL
PETROCAST_SOURCE_WELLS_URL=$SOURCE_WELLS_URL
PETROCAST_NOTIFICATION_WEBHOOK_URL=$NOTIFICATION_WEBHOOK_URL
EOF

# ── Traefik basic-auth middleware (file provider, hot-reloaded) ───────────────
cat > "$DYNAMIC_DIR/auth.yml" <<EOF
http:
  middlewares:
    petrocast-auth:
      basicAuth:
        users:
          - "$BASIC_AUTH_HTPASSWD"
EOF

# ── External networks the compose files expect to pre-exist ──────────────────
docker network create petrocast 2>/dev/null || true
docker network create petrocast_data 2>/dev/null || true

# ── API env file ─────────────────────────────────────────────────────────────
# compose.dev.yml declares `env_file: ../apps/api/.env.example`, which is NOT
# shipped to the host (only /opt/petrocast/ is). Compose refuses to start if the
# path is missing, so materialize a minimal one (API_KEY has a default in
# config; override via the optional SSM param `api_key`).
API_DIR="$(dirname "$COMPOSE_DIR")/apps/api"
APIKEY="$(get_param_opt api_key)"; [ -n "$APIKEY" ] || APIKEY="petrocast-staging"
mkdir -p "$API_DIR"
printf 'API_KEY=%s\n' "$APIKEY" > "$API_DIR/.env.example"

# ── ECR login + pull the two built images ────────────────────────────────────
aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$ECR_REGISTRY"
docker pull "$ECR_REGISTRY/petrocast/data:staging-latest"
docker pull "$ECR_REGISTRY/petrocast/mock-api:staging-latest"

case "$ACTION" in
  up)
    # The serving set the public API needs: the warehouse + the API itself.
    # These must come up regardless of profile.
    dc up -d --no-build data-postgres api
    if [ "$DATA_STACK_PROFILE" = "full" ]; then
      # Heavy, on-demand extras. DataHub is brought up best-effort — a DataHub
      # failure must not block the core serving set.
      dc up -d --no-build dagster metabase
      dc up -d --no-build datahub-mysql datahub-opensearch datahub-kafka \
        datahub-upgrade datahub-gms datahub-frontend datahub-actions \
        || echo "[deploy-data] WARNING: DataHub did not come up cleanly (see its logs)"
      echo "[deploy-data] full data stack up — UIs via Traefik on *.staging.$DOMAIN"
    else
      echo "[deploy-data] core serving set up (postgres + api) — profile=core."
      echo "  Orchestration/catalog/BI run locally; use DATA_STACK_PROFILE=full to add them."
    fi
    ;;
  seed)
    # Populate gold so the API and Metabase have data. Idempotent: re-running
    # a month range overwrites it (silver delete+insert, gold upsert). Assumes
    # the stack is already up (run `up` first). NOTE: bronze re-downloads the
    # full source CSV per partition, so keep the range small.
    # Requires the dagster service — bring the stack up with DATA_STACK_PROFILE=full,
    # or run the pipeline locally (the default cloud profile has no dagster).
    if ! dc ps --status running --services 2>/dev/null | grep -qx dagster; then
      echo "ERROR: dagster is not running (profile=core). Re-run 'up' with"
      echo "  DATA_STACK_PROFILE=full, or seed from a local stack." >&2
      exit 1
    fi
    RANGE="${SEED_RANGE:-2023-01-01...2023-02-01}"
    echo "[deploy-data] seeding partition range $RANGE"
    # `dagster` lives on the container venv PATH (no `uv` in the runtime image);
    # silver/gold go through Dagster's dbt integration (handles partitions).
    dc exec -T dagster dagster asset materialize \
      --module-name petrocast_data.definitions \
      --select "warehouse_schemas_ready,bronze/production_by_well,bronze/wells_registry" \
      --partition-range "$RANGE"
    dc exec -T dagster dagster asset materialize \
      --module-name petrocast_data.definitions \
      --select "tag:silver,tag:gold" \
      --partition-range "$RANGE"
    echo "[deploy-data] seed done. Next (operator): provision Metabase + DataHub ingest"
    echo "  see docs/runbooks/deploy-staging-data.md"
    ;;
  *)
    echo "ERROR: unknown action '$ACTION' (use: up | seed)"; exit 1
    ;;
esac
echo "[$(date -u)] deploy-data.sh done"
