#!/usr/bin/env bash
# Update the hosted stack on the VPS. Run from the repo root:
#
#   ./deploy/deploy.sh
#
# Pulls the latest code and rebuilds/restarts only what changed; database
# migrations run automatically when the api container starts.
set -euo pipefail

cd "$(dirname "$0")/.."

git pull --ff-only
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
docker image prune -f

echo
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
echo "Deployed. Health: curl -fsS https://\$AIP_DOMAIN/health"
