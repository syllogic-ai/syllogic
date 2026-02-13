#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

MODE="local"
MCP_ENABLED="false"

usage() {
  cat <<'EOF'
Usage: dev-up.sh [--local|--prebuilt] [--mcp]

  --local     Build local images (default).
  --prebuilt  Pull GHCR images via deploy/compose.
  --mcp       Enable the MCP service (deploy/compose stack only).
EOF
}

for arg in "$@"; do
  case "$arg" in
    --local)
      MODE="local"
      ;;
    --prebuilt)
      MODE="prebuilt"
      ;;
    --mcp)
      MCP_ENABLED="true"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      usage
      exit 1
      ;;
  esac
done

MCP_PROFILE_ARGS=()
if [ "$MCP_ENABLED" = "true" ]; then
  MCP_PROFILE_ARGS=(--profile mcp)
fi

if [ "$MODE" = "prebuilt" ]; then
  ENV_FILE="$ROOT_DIR/deploy/compose/.env"
  if [ ! -f "$ENV_FILE" ]; then
    echo "Missing $ENV_FILE."
    echo "Copy deploy/compose/.env.example to deploy/compose/.env and edit it first."
    exit 1
  fi

  echo "Pulling prebuilt images (GHCR)..."
  docker compose --env-file "$ENV_FILE" -f "$ROOT_DIR/deploy/compose/docker-compose.yml" pull
  echo "Starting prebuilt stack..."
  docker compose "${MCP_PROFILE_ARGS[@]}" --env-file "$ENV_FILE" -f "$ROOT_DIR/deploy/compose/docker-compose.yml" up -d
  echo "Done."
  exit 0
fi

if [ "$MCP_ENABLED" = "true" ]; then
  ENV_FILE="$ROOT_DIR/deploy/compose/.env"
  if [ ! -f "$ENV_FILE" ]; then
    echo "Missing $ENV_FILE."
    echo "Copy deploy/compose/.env.example to deploy/compose/.env and edit it first."
    exit 1
  fi
  echo "Starting local stack with MCP (build from source)..."
  docker compose "${MCP_PROFILE_ARGS[@]}" \
    --env-file "$ENV_FILE" \
    -f "$ROOT_DIR/deploy/compose/docker-compose.yml" \
    -f "$ROOT_DIR/deploy/compose/docker-compose.local.yml" \
    up -d --build
  echo "Done."
  exit 0
fi

echo "Starting local infrastructure containers..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d --build

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm not found. Install pnpm and rerun:"
  echo "  DATABASE_URL=postgresql://financeuser:financepass@localhost:5433/finance_db pnpm -C \"$ROOT_DIR/frontend\" db:migrate"
  exit 1
fi

# Use a sensible default for local dev if DATABASE_URL isn't already set.
DEFAULT_DB_URL="postgresql://financeuser:financepass@localhost:5433/finance_db"
if [ -z "${DATABASE_URL:-}" ]; then
  export DATABASE_URL="$DEFAULT_DB_URL"
fi

echo "Applying database migrations..."
(cd "$ROOT_DIR/frontend" && pnpm db:migrate)

echo "Done."
