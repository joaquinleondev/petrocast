#!/bin/bash
# Runs on the EC2 via AWS SSM Run Command.
# Triggers Docker Swarm rollback for a specific stack's mock-api service.
#
# Required env vars:
#   STACK_NAME  — stack to rollback (pr-NNN, staging, prod)
#   AWS_REGION  — AWS region (used for logging)
set -euo pipefail
exec > >(tee -a /var/log/deploy.log) 2>&1

SERVICE="${STACK_NAME}_mock-api"
echo "[$(date -u)] Rollback start — service=$SERVICE"

docker service rollback "$SERVICE"

# Wait for rollback to complete
for i in $(seq 1 24); do
  STATE=$(docker service inspect "$SERVICE" \
    --format '{{.UpdateStatus.State}}' 2>/dev/null || echo "")

  case "$STATE" in
    rollback_completed|"")
      echo "Rollback completed (state=$STATE)"
      break
      ;;
    rollback_started|rollback_paused)
      echo "Rollback in progress... ($i/24)"
      ;;
    *)
      echo "Unexpected state after rollback: $STATE" >&2
      ;;
  esac

  sleep 5
done

# Verify health after rollback
HTTP_CODE=$(docker run --rm --network host \
  curlimages/curl:latest curl -s -o /dev/null -w '%{http_code}' \
  "http://localhost:8000/health/ready" 2>/dev/null || echo "000")

if [[ "$HTTP_CODE" == "200" ]]; then
  echo "[$(date -u)] Rollback success — service=$SERVICE healthy"
else
  echo "[$(date -u)] Rollback done but health check returned HTTP $HTTP_CODE" >&2
  exit 1
fi
