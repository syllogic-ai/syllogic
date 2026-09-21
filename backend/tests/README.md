# Backend API Tests

This directory contains integration tests for the backend API endpoints.

## Running Tests Locally

```bash
scripts/test-backend.sh                  # provision + run the whole suite
scripts/test-backend.sh --reset          # rebuild the test database first
scripts/test-backend.sh --setup-only     # provision only, run nothing
scripts/test-backend.sh tests/test_accounts.py -k delete   # extra args go to pytest
```

The script starts the compose `db` and `redis` services if they are down,
creates `finance_test` if it does not exist, applies the Drizzle migrations
and then the backend-only ones in `postgres_migration/`, and only runs pytest
once the schema matches `app/models.py`.

### Why a separate database

`conftest.py` truncates every application table after every single test, so
the suite must never point at `finance_db`. It refuses to: with no
`DATABASE_URL` set it defaults to `finance_test`, and a `DATABASE_URL` naming
a protected database aborts the run (override with
`ALLOW_DESTRUCTIVE_TEST_DB=1` only if wiping it is genuinely what you want).

A stale test database is the usual cause of a run that fails in a different
place each time: the missing column fails the test, the post-test TRUNCATE
then fails too, so state leaks into whatever runs next. `conftest.py` checks
the schema once up front and fails the whole run with the fix instead.

### Running pytest directly

```bash
cd backend
DATABASE_URL=postgresql+psycopg://financeuser:financepass@localhost:5433/finance_test \
  pytest tests/ --timeout=120
```

`conftest.py` starts the compose `db`/`redis` services itself if they are not
answering, so this works from a cold machine -- but it will not migrate a
stale schema for you. Use the script for that.

### Prerequisites
1. Docker (for the Postgres/Redis services the script manages)
2. Python `3.11+` -- `backend/.venv` is used automatically when present
3. A handful of tests talk to a running backend over HTTP on `http://localhost:8000`
   and need `INTERNAL_AUTH_SECRET` set; the script defaults it to
   `test-internal-auth-secret`

### Known failures

`test_holding_valuation_service.py`, `test_investment_sync_service.py`,
`test_investment_tasks.py`, `test_investments_routes.py` and
`test_mcp_investments_tools.py` error at setup: they build their schema on an
in-memory SQLite engine, which cannot compile the JSONB and UUID columns the
models now use. CI excludes these files for the same reason. They need
porting to the shared Postgres `db_session` fixture.

## Test Files

- `test_transaction_import.py` - Tests the transaction import API endpoint
- `test_categorizer.py` - Tests the categorization API (single and batch)
- `test_subscription_identifier.py` - Tests subscription detection functionality
- `test_data_encryption.py` - Tests AES-GCM encryption, key rotation fallback, and blind index generation
- `test_encryption_upgrade.py` - Tests encryption upgrade script coverage + exit-code behavior
- `test_mcp_server_health.py` - Verifies MCP `/health` is public while transport stays auth-protected
- `test_account_sync_encryption.py` - Validates account sync dedupe still works with encrypted `external_id`

## Coverage

```bash
pytest --cov --cov-report=term-missing --cov-report=html
```

Source scope (`app/`, `tasks/`) and omit rules live in `pyproject.toml` under `[tool.coverage.run]`. HTML report writes to `htmlcov/index.html`. Tests that talk to the API over HTTP (against a separately running `uvicorn` process) won't attribute coverage to server-side code the same way in-process tests do — most of this suite calls routes/services directly, so this is a minor gap, not a blocker.

## CI/CD

These tests are automatically run in GitHub Actions on every push and pull request.
