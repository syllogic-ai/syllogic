#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_file() {
  local file="$1"
  if [ ! -f "$file" ]; then
    echo "[contract] Missing required file: $file"
    exit 1
  fi
}

assert_contains() {
  local file="$1"
  local pattern="$2"
  if ! grep -qE "$pattern" "$file"; then
    echo "[contract] Expected pattern not found in $file: $pattern"
    exit 1
  fi
}

require_file "$ROOT_DIR/frontend/railway.toml"
require_file "$ROOT_DIR/backend/railway.api.toml"
require_file "$ROOT_DIR/backend/railway.worker.toml"
require_file "$ROOT_DIR/backend/railway.beat.toml"
require_file "$ROOT_DIR/backend/railway.mcp.toml"
require_file "$ROOT_DIR/scripts/local-smoke.sh"

assert_contains "$ROOT_DIR/docker-compose.yml" "postgres:16-alpine"
assert_contains "$ROOT_DIR/deploy/compose/docker-compose.yml" "postgres:16-alpine"
assert_contains "$ROOT_DIR/deploy/railway/docker-compose.yml" "mcp"
assert_contains "$ROOT_DIR/deploy/railway/docker-compose.yml" "/health"

echo "[contract] Deployment contract checks passed."
