#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/deploy/compose/.env"
MCP_ENABLED="false"

usage() {
  cat <<'EOF'
Usage: prod-up.sh [--mcp]

  --mcp  Enable the MCP service.
EOF
}

for arg in "$@"; do
  case "$arg" in
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

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE."
  echo "Copy deploy/compose/.env.example to deploy/compose/.env and edit it first."
  exit 1
fi

MCP_PROFILE_ARGS=()
if [ "$MCP_ENABLED" = "true" ]; then
  MCP_PROFILE_ARGS=(--profile mcp)
fi

echo "Pulling prebuilt images (GHCR)..."
docker compose --env-file "$ENV_FILE" -f "$ROOT_DIR/deploy/compose/docker-compose.yml" pull

echo "Starting production stack..."
docker compose "${MCP_PROFILE_ARGS[@]}" --env-file "$ENV_FILE" -f "$ROOT_DIR/deploy/compose/docker-compose.yml" up -d

echo "Done."
