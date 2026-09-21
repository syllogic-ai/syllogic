#!/usr/bin/env bash
set -euo pipefail

# Provision the disposable database the backend test suite needs, then run pytest.
#
# tests/conftest.py TRUNCATEs every application table after every single test,
# so the suite must never be pointed at finance_db (the dev database). This
# script owns a separate database -- finance_test by default -- starts the
# docker services if they are not running, applies the same migrations CI
# applies (Drizzle owns the core schema, postgres_migration/ adds the
# backend-only tables and columns on top), and only then runs pytest.
#
# Usage:
#   scripts/test-backend.sh                    # set up, then run the whole suite
#   scripts/test-backend.sh --reset            # drop and rebuild the test database first
#   scripts/test-backend.sh --setup-only       # provision the database, run nothing
#   scripts/test-backend.sh tests/test_foo.py -k bar   # extra args go to pytest

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"

TEST_DB_NAME="${TEST_DB_NAME:-finance_test}"
DB_SERVICE="db"
DB_CONTAINER="finance_db"
DB_USER="financeuser"
DB_PASSWORD="financepass"
DB_HOST_PORT="5433"
REDIS_HOST_PORT="6379"
# Redis database 1, so a test run never flushes whatever the dev stack has in 0.
TEST_REDIS_URL="${TEST_REDIS_URL:-redis://localhost:${REDIS_HOST_PORT}/1}"

RESET=0
SETUP_ONLY=0
PYTEST_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --reset) RESET=1; shift ;;
    --setup-only) SETUP_ONLY=1; shift ;;
    --) shift; PYTEST_ARGS+=("$@"); break ;;
    *) PYTEST_ARGS+=("$1"); shift ;;
  esac
done

log() { echo "[test-backend] $*"; }
fail() { echo "[test-backend] ERROR: $*" >&2; exit 1; }

if [ "$TEST_DB_NAME" = "finance_db" ]; then
  fail "TEST_DB_NAME must not be finance_db -- the suite truncates every table in it."
fi

command -v docker >/dev/null 2>&1 || fail "docker is required but was not found on PATH."

# --- 1. Bring up postgres + redis if they are not already running -----------

ensure_services() {
  local db_state redis_state
  db_state="$(docker compose -f "${ROOT_DIR}/docker-compose.yml" ps --status running --services 2>/dev/null || true)"

  if ! grep -qx "${DB_SERVICE}" <<<"$db_state" || ! grep -qx "redis" <<<"$db_state"; then
    log "starting docker services: ${DB_SERVICE} redis"
    (cd "$ROOT_DIR" && docker compose up -d "${DB_SERVICE}" redis)
  else
    log "docker services already running"
  fi

  log "waiting for postgres to accept connections"
  local waited=0
  until docker exec "$DB_CONTAINER" pg_isready -U "$DB_USER" -d postgres >/dev/null 2>&1; do
    waited=$((waited + 1))
    [ "$waited" -gt 60 ] && fail "postgres did not become ready within 60s."
    sleep 1
  done

  log "waiting for redis"
  waited=0
  until docker exec finance_redis redis-cli ping >/dev/null 2>&1; do
    waited=$((waited + 1))
    [ "$waited" -gt 30 ] && fail "redis did not become ready within 30s."
    sleep 1
  done
}

psql_postgres() { docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres -tAc "$1"; }

# --- 2. Create (or recreate) the test database -----------------------------

FRESH_DB=0

ensure_database() {
  local exists
  exists="$(psql_postgres "SELECT 1 FROM pg_database WHERE datname = '${TEST_DB_NAME}'")"

  if [ "$RESET" = "1" ] && [ "$exists" = "1" ]; then
    log "dropping ${TEST_DB_NAME} (--reset)"
    psql_postgres "DROP DATABASE ${TEST_DB_NAME} WITH (FORCE)" >/dev/null
    exists=""
  fi

  if [ "$exists" != "1" ]; then
    log "creating ${TEST_DB_NAME}"
    psql_postgres "CREATE DATABASE ${TEST_DB_NAME} OWNER ${DB_USER}" >/dev/null
    FRESH_DB=1
  else
    log "${TEST_DB_NAME} already exists"
  fi
}

# --- 3. Schema: Drizzle migrations first, then the backend-only ones -------

# Inside the compose network the database is reachable as db:5432; from the
# host it is localhost:5433.
container_database_url() { echo "postgresql://${DB_USER}:${DB_PASSWORD}@db:5432/${TEST_DB_NAME}"; }
host_database_url() { echo "postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@localhost:${DB_HOST_PORT}/${TEST_DB_NAME}"; }

python_bin() {
  if [ -x "${BACKEND_DIR}/.venv/bin/python" ]; then
    echo "${BACKEND_DIR}/.venv/bin/python"
  else
    echo "python3"
  fi
}

schema_is_current() {
  (cd "$BACKEND_DIR" && DATABASE_URL="$(host_database_url)" "$(python_bin)" \
    scripts/check_schema_drift.py --ignore-extra-columns >/dev/null 2>&1)
}

apply_migrations() {
  log "applying Drizzle migrations to ${TEST_DB_NAME}"
  if ! (cd "$ROOT_DIR" && docker compose run --rm --no-deps \
        -e DATABASE_URL="$(container_database_url)" migrate); then
    if [ "$FRESH_DB" = "0" ]; then
      fail "Drizzle migrations failed. ${TEST_DB_NAME} is most likely in a hand-built state whose
  drizzle.__drizzle_migrations journal does not match its tables, so the replay
  collides with columns that already exist. Rebuild it: scripts/test-backend.sh --reset"
    fi
    fail "Drizzle migrations failed against a freshly created ${TEST_DB_NAME}."
  fi

  log "applying backend schema migrations"
  (cd "$ROOT_DIR" && docker compose run --rm --no-deps \
    -e DATABASE_URL="postgresql+psycopg://${DB_USER}:${DB_PASSWORD}@db:5432/${TEST_DB_NAME}" \
    backend-migrate)
}

ensure_schema() {
  if [ "$FRESH_DB" = "0" ] && schema_is_current; then
    log "schema is already current, skipping migrations"
    return
  fi

  apply_migrations

  if ! schema_is_current; then
    (cd "$BACKEND_DIR" && DATABASE_URL="$(host_database_url)" "$(python_bin)" \
      scripts/check_schema_drift.py --ignore-extra-columns || true)
    fail "${TEST_DB_NAME} still does not match app/models.py after migrating. See the drift report above."
  fi
  log "schema is current"
}

# --- 4. Run the suite ------------------------------------------------------

run_pytest() {
  local py
  py="$(python_bin)"
  if [ "$py" = "python3" ]; then
    log "WARNING: backend/.venv not found, falling back to python3 on PATH"
  fi

  if [ "${#PYTEST_ARGS[@]}" -eq 0 ]; then
    PYTEST_ARGS=(tests/)
  fi

  log "running pytest against ${TEST_DB_NAME}"
  cd "$BACKEND_DIR"
  DATABASE_URL="$(host_database_url)" \
  REDIS_URL="${TEST_REDIS_URL}" \
  INTERNAL_AUTH_SECRET="${INTERNAL_AUTH_SECRET:-test-internal-auth-secret}" \
    exec "$py" -m pytest "${PYTEST_ARGS[@]}" --timeout=120
}

ensure_services
ensure_database
ensure_schema

if [ "$SETUP_ONLY" = "1" ]; then
  log "setup complete. DATABASE_URL=$(host_database_url)"
  exit 0
fi

run_pytest
