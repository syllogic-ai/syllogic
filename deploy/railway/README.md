# Deploy Syllogic to Railway

## One-Click Deploy

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/N98lwA?referralCode=25KFsK&utm_medium=integration&utm_source=template&utm_campaign=generic)

Keep secrets in Railway Shared Variables, not in the URL.

## 1. Import

Drag `docker-compose.yml` (this directory) onto your Railway project canvas.
Railway will create services for: **postgres**, **redis**, **backend**, **mcp**, **worker**, **beat**, **app**.

## 2. Post-Import Configuration

### Set Shared Variables

In Railway's **Shared Variables** UI, set the following. The compose file already references
these using `${{shared.VAR}}` syntax, so all services pick them up automatically.

| Variable | Value | Notes |
|----------|-------|-------|
| `POSTGRES_PASSWORD` | (generate) | `openssl rand -hex 16` |
| `DATABASE_URL` | `postgresql://financeuser:${{shared.POSTGRES_PASSWORD}}@${{postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/finance_db` | Reference variable |
| `REDIS_URL` | `redis://${{redis.RAILWAY_PRIVATE_DOMAIN}}:6379/0` | Reference variable |
| `APP_URL` | `https://${{app.RAILWAY_PUBLIC_DOMAIN}}` | Enable public networking on `app` first |
| `BACKEND_URL` | `http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8080` | Internal networking; backend listens on Railway default PORT (8080) |
| `PORT` (app only) | `3000` | Required so Railway’s proxy routes traffic to the Next.js server |
| `BETTER_AUTH_SECRET` | (generate) | `openssl rand -hex 32` |
| `INTERNAL_AUTH_SECRET` | (generate) | `openssl rand -hex 32` |
| `OPENAI_API_KEY` | (optional) | Your OpenAI key |
| `LOGO_DEV_API_KEY` | (optional) | Your Logo.dev key |

> The compose file uses `${{shared.VAR}}` references — Railway resolves these automatically
> from shared variables. No need to manually edit per-service variables after import.

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

**Fix:** Sync the database password to the value used in `DATABASE_URL`:

1. In Railway, open the **postgres** service → **Connect** (or run `railway connect postgres` from the project directory and choose the postgres service).
2. In the `psql` (or SQL) prompt, run (use the **exact** password from your app’s `DATABASE_URL`; this example uses a placeholder):
   ```sql
   ALTER USER financeuser WITH PASSWORD 'YOUR_ACTUAL_DATABASE_URL_PASSWORD';
   ```
3. Redeploy or restart the **app** (and any other service that uses `DATABASE_URL`) so they reconnect.

**Prevent it next time:** Set `POSTGRES_PASSWORD` (and a `DATABASE_URL` that uses it) **before** the first deploy of the postgres service, so the database is initialized with the correct password.

### If Postgres was removed/re-added and changes are stuck

Railway can leave an extra Postgres service on the canvas (for example, `postgres-<uuid>`) after remove/re-add flows. If your app starts failing with malformed DB URLs, ensure your shared references point to the canonical service name you intend to keep.

1. Keep only one Postgres service for the environment (recommended name: `postgres`).
2. Ensure `DATABASE_URL` resolves from that service:
   - `postgresql://financeuser:${{shared.POSTGRES_PASSWORD}}@${{postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/finance_db`
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
- **App port**: Set `PORT=3000` on the app service so Railway’s proxy forwards traffic to the correct port.

If your existing app service is mounted at `/data/uploads`, profile images can fail to persist or render. Move that volume mount to `/app/public/uploads` and redeploy `app`.

## 7. What Was Removed (vs Self-Hosted Compose)

| Service | Reason |
|---------|--------|
| `caddy` | Railway provides reverse proxy + automatic TLS |
| `uploads-init` | Replaced by app startup (`mkdir -p /app/public/uploads`) and `RAILWAY_RUN_UID=0` on Railway |
| `migrate` | Replaced by pre-deploy command on `app` service |

## 8. Updating

Update the image tags directly on each service in the Railway dashboard (or edit this compose file and re-import). Railway's `${{shared.VAR}}` syntax is only supported in environment variables, not in `image` fields.
