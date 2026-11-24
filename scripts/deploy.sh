#!/usr/bin/env bash
# Rebuild and restart services, then restart the gateway: nginx keeps the addresses the containers had when it started,
# so after a container is recreated it answers 502 until it is restarted.
# usage: scripts/deploy.sh [service ...]   (default: the whole stack)
set -euo pipefail
cd "$(dirname "$0")/.."
services=("$@")
compose=(docker compose --env-file .env -f shared/infra/docker-compose.yml)
"${compose[@]}" build ${services[@]+"${services[@]}"}
"${compose[@]}" up -d --no-build ${services[@]+"${services[@]}"}
"${compose[@]}" restart gateway
for _ in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ || true)
  [ "$code" = "200" ] && { echo "gateway answers 200"; exit 0; }
  sleep 2
done
echo "gateway did not answer 200 (last: $code)" >&2
exit 1
