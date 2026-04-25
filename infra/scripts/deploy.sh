#!/bin/bash
# Runs on the EC2 via AWS SSM Run Command (AWS-RunShellScript).
# All variables below come from the SSM command environment.
#
# Required env vars (set by GitHub Actions workflow):
#   IMAGE_URI    — full ECR image URI with tag
#   STACK_NAME   — stack identifier (pr-NNN, staging, prod)
#   HOSTNAME     — FQDN for Traefik routing
#   REPLICAS     — replica count (1=preview, 2=staging/prod)
#   ENV          — environment label
#   API_KEY      — API authentication key (from GitHub Secret)
#   AWS_REGION   — AWS region
#   ECR_REGISTRY — ECR registry host (account.dkr.ecr.region.amazonaws.com)
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
exec > >(tee -a /var/log/deploy.log) 2>&1

echo "[$(date -u)] Deploy start — stack=$STACK_NAME image=$IMAGE_URI"

# ── ECR authentication ────────────────────────────────────────────────────────
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# ── Render stack template ─────────────────────────────────────────────────────
RENDERED="/tmp/stack-${STACK_NAME}.yml"

# Substitute all declared template variables; leave any unknown ${} patterns untouched.
envsubst '${IMAGE_URI} ${STACK_NAME} ${HOSTNAME} ${REPLICAS} ${ENV} ${API_KEY} ${AWS_REGION}' \
  < /opt/petrocast/mock-api.stack.yml > "$RENDERED"

# ── Deploy ────────────────────────────────────────────────────────────────────
docker stack deploy -c "$RENDERED" "$STACK_NAME" --with-registry-auth

# ── Wait for rolling update to converge ──────────────────────────────────────
echo "Waiting for Swarm rolling update..."
SERVICE="${STACK_NAME}_mock-api"

for i in $(seq 1 36); do
  STATE=$(docker service inspect "$SERVICE" \
    --format '{{.UpdateStatus.State}}' 2>/dev/null || echo "new")

  case "$STATE" in
    completed|new|"")
      echo "Service converged (state=$STATE)"
      break
      ;;
    rollback_completed|rollback_started|rollback_paused)
      echo "Swarm rolled back the service (state=$STATE)" >&2
      exit 1
      ;;
    updating|preparing)
      echo "Still updating... ($i/36)"
      ;;
    paused)
      echo "Update paused by Swarm — check service health" >&2
      exit 1
      ;;
  esac

  sleep 5
done

# ── Health check ──────────────────────────────────────────────────────────────
echo "Running health check..."
for attempt in $(seq 1 12); do
  HTTP_CODE=$(docker run --rm --network host \
    curlimages/curl:latest curl -s -o /dev/null -w '%{http_code}' \
    "http://localhost:8000/health/ready" 2>/dev/null || echo "000")

  if [[ "$HTTP_CODE" == "200" ]]; then
    echo "Health check passed (HTTP $HTTP_CODE)"
    break
  fi

  if [[ "$attempt" -eq 12 ]]; then
    echo "Health check failed after 12 attempts (last HTTP $HTTP_CODE)" >&2
    exit 1
  fi

  echo "Health not ready yet — HTTP $HTTP_CODE (attempt $attempt/12)"
  sleep 5
done

echo "[$(date -u)] Deploy success — stack=$STACK_NAME"
