# PostgreSQL Migration Tools

This directory contains database administration and migration tools for PostgreSQL.

## Files

- **`monitor_db.py`** - Streamlit app for monitoring and inspecting the database
  - Run with: `streamlit run postgres_migration/monitor_db.py` (from the `backend` directory)
  - Provides a web UI to view all tables, filter data, and monitor database updates

- **`reset_database.py`** - Script to reset the database by dropping all tables and recreating them
  - Run with: `python postgres_migration/reset_database.py` (from the `backend` directory)
  - ⚠️ **WARNING**: This will delete all existing data!
  - Useful for development when you need to recreate tables with updated schema

- **`backfill_encrypted_fields.py`** - Backfills encrypted columns for sensitive fields
  - Run with: `python postgres_migration/backfill_encrypted_fields.py --batch-size 500`
  - Requires `DATA_ENCRYPTION_KEY_CURRENT` and `DATA_ENCRYPTION_KEY_ID`
  - Encrypts `accounts.external_id` and `csv_imports.file_path`
  - Optional plaintext cutover: add `--clear-plaintext`

- **`run_encryption_upgrade.py`** - One-command migration/backfill orchestrator
  - Run with: `python postgres_migration/run_encryption_upgrade.py --batch-size 500`
  - Validates encryption key configuration
  - Runs backfill using `backfill_encrypted_fields.py`
  - Prints coverage counters for `accounts` and `csv_imports`
  - Exits non-zero when coverage is incomplete
  - Supports `--dry-run` and `--clear-plaintext`

- **`seed_demo_data.py`** - Shared demo user seeding/reset tool
  - Run with: `python postgres_migration/seed_demo_data.py --user-email demo@example.com --mode reset`
  - Generates deterministic realistic data from Jan 1, 2025 to today (or custom range)
  - Seeds at least 3 accounts including a non-EUR account
  - Populates category-level categorization instructions
  - Recomputes functional amounts, balances, and account timeseries
  - Preserves BetterAuth records (user/session/auth tables) and only resets financial data

## Usage

All scripts should be run from the `backend` directory:

```bash
cd backend

# Monitor database
streamlit run postgres_migration/monitor_db.py

# Reset database (WARNING: deletes all data!)
python postgres_migration/reset_database.py

# Backfill encrypted field columns
python postgres_migration/backfill_encrypted_fields.py --batch-size 500

# Optional cutover step (clear plaintext columns after validation)
python postgres_migration/backfill_encrypted_fields.py --batch-size 500 --clear-plaintext

# One-command upgrade for existing installs (recommended)
python postgres_migration/run_encryption_upgrade.py --batch-size 500

# Dry-run coverage check
python postgres_migration/run_encryption_upgrade.py --batch-size 500 --dry-run

# Optional cutover: clear plaintext after validation window
python postgres_migration/run_encryption_upgrade.py --batch-size 500 --clear-plaintext

# Seed/reset shared demo data (existing user required)
python postgres_migration/seed_demo_data.py \
  --user-email demo@example.com \
  --from-date 2025-01-01 \
  --to-date 2026-03-01 \
  --mode reset
```

## Note

These are development/admin tools. The actual application code uses:
- `app/db_helpers.py` - Application-level database helpers
- `app/database.py` - Database connection configuration
- `app/models.py` - SQLAlchemy models

## Demo Reset Automation

Nightly demo reset is available through Celery Beat when these variables are enabled:

- `DEMO_MODE=true`
- `DEMO_RESET_ENABLED=true`
- `DEMO_SHARED_USER_EMAIL` (or `DEMO_SHARED_USER_ID`)
- `DEMO_RESET_HOUR_UTC=0` (00:00 UTC by default)
- `DEMO_SEED_RANDOM_SEED=42` (deterministic dataset)

When enabled, Beat schedules task `tasks.demo_tasks.reset_demo_environment` daily at minute `0` of the configured UTC hour.

Daily demo transaction growth is also available:

- `DEMO_DAILY_ENGINE_ENABLED=true`
- `DEMO_DAILY_ENGINE_HOUR_UTC=2`
- `DEMO_DAILY_ENGINE_MINUTE_UTC=15`

When enabled, Beat schedules task `tasks.demo_tasks.append_previous_day_demo_transactions`,
which first checks/fills date gaps in demo coverage and then appends transactions for yesterday
(skipping if that day is already populated).
If demo financial foundation is missing (accounts/categories/transactions) or gaps are large,
the coverage step performs a full reset seed from `DEMO_DEFAULT_START_DATE` through today.
