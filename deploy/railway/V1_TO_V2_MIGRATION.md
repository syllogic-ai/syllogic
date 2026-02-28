# Railway Template Migration: V1 (Image) to V2 (GitHub Source)

This guide migrates an existing Railway deployment from the v1 image-based template to the v2 source-service model.

## Goals

1. Keep production stable while moving app services to GitHub source.
2. Keep data services on Railway plugins (Postgres + Redis).
3. Preserve secrets/encryption contract.

## Pre-migration Checklist

1. Confirm backups exist for Postgres.
2. Confirm shared vars are set:
   - `BETTER_AUTH_SECRET`
   - `INTERNAL_AUTH_SECRET`
   - `DATA_ENCRYPTION_KEY_CURRENT`
   - `DATA_ENCRYPTION_KEY_ID`
3. Confirm app is healthy on v1.

## Service Mapping

| Service | Root | Config path |
|---|---|---|
| app | `/frontend` | `/frontend/railway.toml` |
| backend | `/backend` | `/backend/railway.api.toml` |
| worker | `/backend` | `/backend/railway.worker.toml` |
| beat | `/backend` | `/backend/railway.beat.toml` |
| mcp | `/backend` | `/backend/railway.mcp.toml` |

## Migration Steps

1. Create a new Railway environment for validation.
2. Add Railway Postgres and Redis plugins in that environment.
3. Add the five source services using the mapping table above.
4. Set service root and config path for each service exactly.
5. Reuse the same shared secrets/encryption variables.
6. Validate:
   - app signup/login
   - account sync/import
   - worker/beat activity
   - mcp `/health` returns `200`
7. Cut over traffic to v2 app service.
8. Keep v1 services as rollback path for a stabilization window.

## Post-cutover

1. Run encryption coverage command on existing installs:

```bash
python postgres_migration/run_encryption_upgrade.py --batch-size 500
```

2. Check logs for decrypt errors.
3. Decommission v1 services after stable monitoring window.
