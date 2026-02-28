#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/deploy/compose/.env"

usage() {
  cat <<'EOF'
Usage: prod-up.sh
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

if [ "$#" -gt 0 ]; then
  echo "Unknown option: $1"
  usage
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE."
  echo "Copy deploy/compose/.env.example to deploy/compose/.env and edit it first."
  exit 1
fi

APP_VERSION_VALUE="$(grep -E '^APP_VERSION=' "$ENV_FILE" | tail -n1 | cut -d'=' -f2- || true)"
if [ "${APP_VERSION_VALUE:-edge}" = "edge" ]; then
  echo "WARNING: APP_VERSION=edge is intended for development/testing."
  echo "For production, pin APP_VERSION to a release tag (for example vX.Y.Z)."
fi

echo "Pulling prebuilt images (GHCR)..."
docker compose --env-file "$ENV_FILE" -f "$ROOT_DIR/deploy/compose/docker-compose.yml" pull

echo "Starting production stack..."
docker compose --env-file "$ENV_FILE" -f "$ROOT_DIR/deploy/compose/docker-compose.yml" up -d

echo "Done."
