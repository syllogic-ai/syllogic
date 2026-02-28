#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${1:-/opt/syllogic}"
ENV_FILE="$INSTALL_DIR/.env"
COMPOSE_FILE="$INSTALL_DIR/docker-compose.yml"

if [ ! -f "$ENV_FILE" ] || [ ! -f "$COMPOSE_FILE" ]; then
  echo "Expected $ENV_FILE and $COMPOSE_FILE."
  echo "Usage: $0 [/opt/syllogic]"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

POSTGRES_USER="${POSTGRES_USER:-financeuser}"
POSTGRES_DB="${POSTGRES_DB:-finance_db}"

compose_cmd() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

echo "[check] Services:"
compose_cmd ps

echo "[check] Health endpoints:"
curl -fsS "${APP_URL%/}/api/health" >/dev/null
echo "  - app/api health: ok"
curl -fsS "http://localhost:${MCP_PORT:-8001}/health" >/dev/null
echo "  - mcp health: ok"

echo "[check] Encryption env contract:"
if [ -z "${DATA_ENCRYPTION_KEY_CURRENT:-}" ] || [ -z "${DATA_ENCRYPTION_KEY_ID:-}" ]; then
  echo "  - missing DATA_ENCRYPTION_KEY_CURRENT or DATA_ENCRYPTION_KEY_ID"
  exit 1
fi
echo "  - encryption keys present"

echo "[check] Migration table exists:"
compose_cmd exec -T postgres sh -lc \
  "psql -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\" -c \"select count(*) from drizzle.__drizzle_migrations;\""

echo "[check] Backup command sanity check:"
compose_cmd exec -T postgres sh -lc \
  "pg_dump -U \"$POSTGRES_USER\" \"$POSTGRES_DB\" --schema-only >/dev/null"
echo "  - pg_dump schema-only: ok"

echo "[check] All post-install checks passed."
