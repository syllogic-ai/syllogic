# Deploy Syllogic to Railway

## One-Click Deploy

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/N98lwA?referralCode=25KFsK&utm_medium=integration&utm_source=template&utm_campaign=generic)

Keep secrets in Railway Shared Variables, not in the URL.

## Template Channels

1. `railway-v1` (current button): image-based compose template in this folder.
2. `railway-v2` (target): GitHub-source services for `app/backend/worker/beat/mcp` plus Railway Postgres/Redis plugins.

Use v1 for compatibility while v2 is rolled out in parallel.

## 1. Import (V1 Image Template)

Drag `docker-compose.yml` (this directory) onto your Railway project canvas.
Railway will create services for: **postgres**, **redis**, **backend**, **mcp**, **worker**, **beat**, **app**.

For v2 source-template setup, see section "Source-Service Config Mapping (V2)" below.

## 2. Post-Import Configuration

### Set Shared Variables

In Railway's **Shared Variables** UI, set the following. The compose file already references
these using `${{shared.VAR}}` syntax, so all services pick them up automatically.

If you previously created shared `DATABASE_URL`, `REDIS_URL`, `APP_URL`, or `BACKEND_URL`,
remove them to avoid overriding compose-derived values.

| Variable | Value | Notes |
|----------|-------|-------|
| `POSTGRES_PASSWORD` | (generate) | `openssl rand -hex 16` |
| `BETTER_AUTH_SECRET` | (generate) | `openssl rand -hex 32` |
| `INTERNAL_AUTH_SECRET` | (generate) | `openssl rand -hex 32` |
| `DATA_ENCRYPTION_KEY_CURRENT` | (generate) | 32-byte base64 or hex key for app-level field encryption |
| `DATA_ENCRYPTION_KEY_PREVIOUS` | (optional) | previous key for decryption during key rotation |
| `DATA_ENCRYPTION_KEY_ID` | `k1` | key identifier embedded in encrypted payloads |
| `OPENAI_API_KEY` | (optional) | Your OpenAI key |
| `LOGO_DEV_API_KEY` | (optional) | Your Logo.dev key |

> The compose file derives `DATABASE_URL`, `REDIS_URL`, `APP_URL`, and `BACKEND_URL`
> directly in service environment blocks using Railway service references. Do not set those
> as shared variables.

This template intentionally requires **shared variables only** for user-provided inputs.
Ports are hardcoded in compose (`app=3000`, `backend=8080`, `mcp=8001`) so users do not
need to configure service-scoped port variables manually.

### Optional Integrations (behavior when unset)

- `OPENAI_API_KEY`: optional. AI categorization features are disabled if unset.
- `LOGO_DEV_API_KEY`: optional. Logo lookup/enrichment features are disabled if unset.
- Services still deploy without these variables.

### Enable Public Networking

- **app**: Enable HTTP public networking (this is your frontend).
- **mcp** (optional): Enable TCP proxy on port 8001 if you need external MCP access.
- All other services should remain **private only**.

### Confirm Service Start Commands (important for worker/beat)

After import, open each service in Railway and verify the effective start command is correct:

- `backend`: default image command (gunicorn API)
- `worker`: `celery -A celery_app worker --loglevel=info --concurrency=4`
- `beat`: `celery -A celery_app beat --loglevel=info`
- `mcp`: `uvicorn mcp_server:app --host 0.0.0.0 --port 8001`
- `app`: `/bin/sh -lc "mkdir -p /app/public/uploads && node scripts/migrate.js && exec node_modules/.bin/next start -p 3000 -H 0.0.0.0"`

If `worker` or `beat` logs show `gunicorn`, they are running the wrong command.
Set the service start command in Railway dashboard and redeploy that service.

### Automatic DB migrations (sign-up/auth safe)

The app must run database migrations so BetterAuth tables (`users`, `sessions`, `auth_accounts`) exist. Without this, **Create account** fails.

- **Compose import (image deploy):** `deploy/railway/docker-compose.yml` runs migrations automatically in the app startup command:
  `node scripts/migrate.js && next start ...`
- **Source deploy (GitHub/template/`railway up` from `frontend/`):** `frontend/railway.toml` sets `preDeployCommand = "node scripts/migrate.js"`.

No manual migration setup is required in either mode.

### Configure Healthcheck Path

Railway can use the healthcheck from the compose file, but you can also set it in the UI:

- **app**: `/`
- **backend**: `/health`
- **mcp**: `/health`

## 3. Alternative: Use Railway Plugins for Postgres & Redis

Instead of the `postgres` and `redis` services from compose, you can use Railway's built-in database plugins:

1. Delete the `postgres` and `redis` services from the canvas.
2. Add **PostgreSQL** and **Redis** plugins from Railway's service menu.
3. Update `DATABASE_URL` and `REDIS_URL` to reference the plugin variables:
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `REDIS_URL=${{Redis.REDIS_URL}}`

This is recommended for production — Railway plugins include automated backups and monitoring.

## 4. Networking Notes

Railway uses internal DNS (`SERVICE_NAME.railway.internal:PORT`) instead of Docker Compose service names. When using reference variables like `${{backend.RAILWAY_PRIVATE_DOMAIN}}`, Railway handles this automatically.

## 5. "Failed to create account" / "password authentication failed for user financeuser"

If sign-up fails and deploy logs show `password authentication failed for user "financeuser"` (code `28P01`), the app’s `DATABASE_URL` password does not match the password stored in the Postgres data. That often happens when Postgres was first deployed with a placeholder (e.g. `CHANGE_ME`) and variables were updated later; the variable changes, but the existing database keeps the old password.

**Fix:** Sync the database password to the value derived from `POSTGRES_PASSWORD`:

1. In Railway, open the **postgres** service → **Connect** (or run `railway connect postgres` from the project directory and choose the postgres service).
2. In the `psql` (or SQL) prompt, run (use the **exact** value currently set in shared `POSTGRES_PASSWORD`; this example uses a placeholder):
   ```sql
   ALTER USER financeuser WITH PASSWORD 'YOUR_ACTUAL_DATABASE_URL_PASSWORD';
   ```
3. Redeploy or restart the **app** (and any other service that uses `DATABASE_URL`) so they reconnect.

**Prevent it next time:** Set `POSTGRES_PASSWORD` **before** the first deploy of the postgres service, so the database is initialized with the correct password.

### If Postgres was removed/re-added and changes are stuck

Railway can leave an extra Postgres service on the canvas (for example, `postgres-<uuid>`) after remove/re-add flows. If your app starts failing with malformed DB URLs, ensure your shared references point to the canonical service name you intend to keep.

1. Keep only one Postgres service for the environment (recommended name: `postgres`).
2. Ensure the compose still derives `DATABASE_URL` from:
   - `postgresql://financeuser:${{shared.POSTGRES_PASSWORD}}@${{postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/finance_db?sslmode=require`
3. Redeploy `app`, `backend`, `worker`, `beat`, and `mcp` after reference cleanup.

### Reset Postgres completely

To wipe the database and re-initialize it with the **current** `POSTGRES_PASSWORD` (so app and DB passwords match):

1. In Railway dashboard, open the **postgres** service.
2. Go to **Settings** (or **Variables** → **Volumes**). Find the volume attached to postgres (e.g. `postgres_data`).
3. **Detach** the volume from the postgres service, then **delete** the volume. (Deleting may be available only in the dashboard; CLI `railway volume delete` can fail with "Problem processing request".)
4. **Add a new volume** to the postgres service with mount path `/var/lib/postgresql/data`. Use a **different name** (e.g. `postgres_data_fresh`) — Railway does not allow two volumes with the same name in a project; the name is just a label. In the dashboard: postgres service → **+ New** → **Volume** → name e.g. `postgres_data_fresh`, mount path `/var/lib/postgresql/data`.
5. **Redeploy** the postgres service. Postgres will start with an empty data directory and create the DB using the current `POSTGRES_PASSWORD`.
6. **Redeploy the app** (and any other service that uses `DATABASE_URL`) so the pre-deploy migrations run and auth works again.

All existing data in Postgres will be lost.

## 6. Uploads volume and app port

- **Volume mount**: The compose mounts uploads at `/app/public/uploads` so files are immediately served from `/uploads/...`.
- **Permissions**: The app service sets `RAILWAY_RUN_UID=0` so first-boot writes to mounted volumes work without manual `chown`.
- **App port**: `PORT=3000` is already hardcoded in compose for the `app` service.
- **Startup hardening**: The app startup command creates `profile/`, `logos/`, and `imports/` folders under `/app/public/uploads` and applies write permissions before running migrations and starting Next.js.
- **Healthcheck hardening**: The app healthcheck verifies `/app/public/uploads` is writable before checking HTTP readiness.

If your existing app service is mounted at `/data/uploads`, profile images can fail to persist or render. Move that volume mount to `/app/public/uploads` and redeploy `app`.

## 7. What Was Removed (vs Self-Hosted Compose)

| Service | Reason |
|---------|--------|
| `caddy` | Railway provides reverse proxy + automatic TLS |
| `uploads-init` | Replaced by app startup (`mkdir -p /app/public/uploads`) and `RAILWAY_RUN_UID=0` on Railway |
| `migrate` | Replaced by app startup command (`node scripts/migrate.js`) |

## 8. Updating and Channel Policy

Channel policy:
1. `edge` is development/testing only.
2. `vX.Y.Z` is for production, self-host, and published templates.

V1 update process:
1. Pin each image to a release tag (e.g. `vX.Y.Z`) in compose.
2. Re-import compose (or update each Railway service image tag in dashboard).
3. Redeploy all app services (`app`, `backend`, `worker`, `beat`, `mcp`).

Railway's `${{shared.VAR}}` syntax is only supported in environment variables, not in `image` fields.

### Source-Service Config Mapping (V2)

When running Railway source services from this monorepo, set root directories and config paths explicitly.

| Service | Root directory | Config path | Notes |
|---|---|---|---|
| `app` | `/frontend` | `/frontend/railway.toml` | Runs predeploy migrations + app start command. |
| `backend` | `/backend` | `/backend/railway.api.toml` | API start + `/health` check. |
| `worker` | `/backend` | `/backend/railway.worker.toml` | Celery worker start command. |
| `beat` | `/backend` | `/backend/railway.beat.toml` | Celery beat start command. |
| `mcp` | `/backend` | `/backend/railway.mcp.toml` | MCP start + `/health` check. |

For v2, use Railway Postgres/Redis plugins and wire `DATABASE_URL`/`REDIS_URL` from plugin references.

### V1 -> V2 Migration Guide (Template Consumers)

1. Create a new environment or project for v2 validation.
2. Stand up source services with the config mapping table above.
3. Use Railway Postgres/Redis plugins in v2.
4. Reuse shared secrets (`BETTER_AUTH_SECRET`, `INTERNAL_AUTH_SECRET`, encryption keys).
5. Run smoke flow:
   - app signup/login
   - account sync/import
   - worker/beat activity
   - MCP `/health` = `200`, unauthenticated `/mcp` rejected
6. Cut over public traffic after validation.
7. Keep v1 available for rollback during a stabilization window.

## 9. Existing-Install Encryption Upgrade

For environments that already contain plaintext `accounts.external_id` or `csv_imports.file_path` values, run a one-command upgrade from the **backend** service shell:

```bash
python postgres_migration/run_encryption_upgrade.py --batch-size 500
```

What it does:
- validates `DATA_ENCRYPTION_KEY_CURRENT` and `DATA_ENCRYPTION_KEY_ID`
- runs the encrypted field backfill
- prints coverage counters for accounts/csv imports
- exits non-zero if coverage is incomplete

Optional:

```bash
# Coverage check without writing
python postgres_migration/run_encryption_upgrade.py --batch-size 500 --dry-run

# Clear plaintext columns after validation window
python postgres_migration/run_encryption_upgrade.py --batch-size 500 --clear-plaintext
```

## 10. Release Operator Checklist

Use this gate before and after a production deploy:

1. Confirm target artifact
   - Railway services point to the intended image tag/digest (prefer pinned `vX.Y.Z`).
2. Confirm migration success
   - `app` deploy logs include successful `node scripts/migrate.js` completion.
3. Confirm encryption coverage (for upgraded environments)
   - Run `python postgres_migration/run_encryption_upgrade.py --batch-size 500`.
   - Command exits `0` with zero missing-encryption counters.
4. Confirm MCP health
   - `mcp` healthcheck path is `/health`.
   - `GET /health` returns `200` with `{"status":"healthy","service":"mcp"}`.
5. Confirm runtime stability
   - app/account sync and assets pages load.
   - no decryption errors in backend logs.
6. Confirm deployment contract gate
   - run `scripts/verify-deploy-contract.sh`.
7. Confirm rollback readiness
   - previous release/service config can be restored if the new deploy regresses.

## 11. Template Guarantees

This Railway template guarantees:

- Shared-variable-first setup (no required per-service variable bootstrapping).
- Private networking by default for internal service-to-service traffic.
- No bind mounts and no host-path dependencies.
- Exactly one persistent volume per stateful service:
  - `postgres` -> `/var/lib/postgresql/data`
  - `redis` -> `/data`
  - `app` -> `/app/public/uploads`
- No Docker Compose-only orchestration assumptions (`depends_on`, `container_name`).

## 12. Compliance Checklist (Railway Best Practices)

Use this checklist before publishing template changes:

1. Compose import compatibility
   - No bind mounts, no host filesystem paths.
   - Service graph deploys independently (no `depends_on` assumptions).
2. Variable model
   - Required onboarding values are shared variables only.
   - Reference variables use Railway template syntax (`${{shared.*}}`, `${{service.*}}`).
3. Networking
   - Public networking enabled only on intended public services (`app`, optional `mcp`).
   - Internal calls use private networking domains.
4. Volumes
   - One volume attached per stateful service.
   - Mount paths match service runtime expectations.
   - `RAILWAY_RUN_UID=0` set where non-root images must write to mounted paths.
5. Runtime commands
   - `worker` and `beat` override command correctly.
   - `app` runs migrations before Next.js startup.
6. Release hygiene
   - Published template images pinned to release tags.
   - Docs updated when variable contract or service wiring changes.

## 13. Validation Procedure

### Static validation

1. Confirm `deploy/railway/docker-compose.yml` has:
   - shared var references for required config
   - private-domain references for internal URLs
   - no bind mounts / no `depends_on` / no `container_name`
2. Confirm docs only require shared vars during initial setup.

### Runtime validation (after import)

1. Variables
   - Set required shared variables once.
   - Confirm no extra required per-service variable prompts.
2. Volumes
   - `postgres` mounted at `/var/lib/postgresql/data`
   - `redis` mounted at `/data`
   - `app` mounted at `/app/public/uploads`
3. Commands/logs
   - `worker` logs show Celery worker boot
   - `beat` logs show Celery beat boot
   - `app` logs show migrations then Next.js boot
   - `backend` logs show API process listening on expected internal port
   - `mcp` health endpoint returns `200` on `/health`
   - `app` healthcheck passes and confirms write access to `/app/public/uploads`
4. Connectivity
   - `app` reaches backend via private networking URL
   - Internal-only services are not publicly exposed unless intentional

### Optional-feature validation

1. Unset `OPENAI_API_KEY` and `LOGO_DEV_API_KEY`.
2. Verify services still boot successfully.
3. Verify optional UI/feature paths degrade gracefully without startup failures.

### Asset persistence validation (logos/profile photos)

1. Upload a profile photo in onboarding/settings, refresh, then hard-reload.
2. Confirm the saved path in DB starts with `/uploads/profile/`.
3. Trigger logo fetch for a subscription/company.
4. Confirm logo paths in DB start with `/uploads/logos/`.
5. Redeploy `app`, then verify both profile photos and logos still render (proves volume-backed persistence).
