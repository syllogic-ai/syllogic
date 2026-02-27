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
```

## Note

These are development/admin tools. The actual application code uses:
- `app/db_helpers.py` - Application-level database helpers
- `app/database.py` - Database connection configuration
- `app/models.py` - SQLAlchemy models
