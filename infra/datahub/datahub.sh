#!/usr/bin/env bash
# datahub.sh — helper on-demand para el stack de gobierno DataHub (F2-21)
#
# Uso:
#   infra/datahub/datahub.sh up      — levanta el stack en background
#   infra/datahub/datahub.sh ingest  — corre ingesta dbt + postgres
#   infra/datahub/datahub.sh down    — baja el stack
#   infra/datahub/datahub.sh status  — estado de los contenedores
#
# Correr desde la raíz del repo.

set -euo pipefail

COMPOSE_FILE="infra/compose.datahub.yml"
ENV_FILE="apps/data/.env"
RECIPES_DIR="infra/datahub/recipes"

# CLI de ingesta — se descarga al vuelo con uvx (no requiere instalar nada)
DATAHUB_DBT_CMD="uvx --from 'acryl-datahub[dbt,datahub-rest]' datahub"
DATAHUB_PG_CMD="uvx --from 'acryl-datahub[postgres,datahub-rest]' datahub"

usage() {
    echo "Uso: $0 {up|ingest|down|status}"
    exit 1
}

cmd_up() {
    echo "==> Levantando stack DataHub..."
    if [ -f "$ENV_FILE" ]; then
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d
    else
        echo "ADVERTENCIA: $ENV_FILE no encontrado, usando defaults de compose."
        docker compose -f "$COMPOSE_FILE" up -d
    fi
    echo ""
    echo "Esperando healthchecks (~2-3 min)..."
    echo "Correr '$0 status' para ver el estado."
    echo "UI disponible en http://localhost:${PETROCAST_DATAHUB_PORT:-9002} (user: datahub / pass: datahub)"
}

cmd_ingest() {
    echo "==> Ingesta dbt (F2-19 requerido — manifest.json + catalog.json)..."
    if [ ! -f "apps/data/dbt/target/manifest.json" ]; then
        echo "ERROR: apps/data/dbt/target/manifest.json no encontrado."
        echo "Generar con: cd apps/data && uv run dbt docs generate --project-dir dbt --profiles-dir dbt"
        exit 1
    fi
    $DATAHUB_DBT_CMD ingest -c "$RECIPES_DIR/dbt.yml"

    echo ""
    echo "==> Ingesta PostgreSQL (bronze/silver/gold + row counts)..."
    $DATAHUB_PG_CMD ingest -c "$RECIPES_DIR/postgres.yml"

    echo ""
    echo "Ingesta completada. Navegar en http://localhost:${PETROCAST_DATAHUB_PORT:-9002}"
}

cmd_down() {
    echo "==> Bajando stack DataHub (liberando RAM)..."
    docker compose -f "$COMPOSE_FILE" down
}

cmd_status() {
    docker compose -f "$COMPOSE_FILE" ps
}

case "${1:-}" in
    up)      cmd_up ;;
    ingest)  cmd_ingest ;;
    down)    cmd_down ;;
    status)  cmd_status ;;
    *)       usage ;;
esac
