#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/deploy/compose/.env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE."
  echo "Copy deploy/compose/.env.example to deploy/compose/.env and set required secrets first."
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

POSTGRES_USER="${POSTGRES_USER:-financeuser}"
POSTGRES_DB="${POSTGRES_DB:-finance_db}"

compose_cmd() {
  docker compose \
    --env-file "$ENV_FILE" \
    -f "$ROOT_DIR/deploy/compose/docker-compose.yml" \
    -f "$ROOT_DIR/deploy/compose/docker-compose.local.yml" \
    "$@"
}

echo "[smoke] Starting local stack from source..."
compose_cmd up -d --build

echo "[smoke] Waiting for app/backend/mcp health..."
timeout 180 bash -c 'until curl -fsS http://localhost:8080/ >/dev/null; do sleep 2; done'
timeout 180 bash -c 'until curl -fsS http://localhost:8080/api/health >/dev/null; do sleep 2; done'
timeout 180 bash -c 'until curl -fsS http://localhost:8001/health >/dev/null; do sleep 2; done'

echo "[smoke] Verifying Drizzle migration table exists..."
compose_cmd exec -T postgres sh -lc \
  "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -c \"select count(*) as migration_rows from drizzle.__drizzle_migrations;\""

echo "[smoke] Verifying encryption helper roundtrip..."
compose_cmd exec -T backend python tests/test_data_encryption.py

echo "[smoke] All checks passed."
