# Self-Hosted (Production) Docker Compose

This directory contains the production-grade Docker Compose bundle:

- PostgreSQL 16
- Redis 7
- FastAPI backend + Celery worker/beat
- Next.js app
- Caddy reverse proxy (TLS by default)
- One-shot Drizzle migration job (runs on deploy/boot)

## Quick Start

1. Copy `deploy/compose/.env.example` to `deploy/compose/.env`.
2. Edit `.env` values (at minimum: `POSTGRES_PASSWORD`, `BETTER_AUTH_SECRET`, `INTERNAL_AUTH_SECRET`).
   - **CRITICAL**: Set a strong `POSTGRES_PASSWORD` (e.g., `openssl rand -hex 32`).
   - **IMPORTANT**: The `DATABASE_URL` value **must use the same password** you set in `POSTGRES_PASSWORD`. The format is `postgresql://financeuser:YOUR_PASSWORD@postgres:5432/finance_db` where `YOUR_PASSWORD` matches `POSTGRES_PASSWORD`.
   - Generate secrets:
     - `BETTER_AUTH_SECRET`: `openssl rand -hex 32`
     - `INTERNAL_AUTH_SECRET`: `openssl rand -hex 32`
   - `APP_URL` defaults to `http://localhost:8080`.
   - `HTTP_PORT` defaults to `8080` in the example env for a conflict-free local default.
   - For a real domain, set `APP_URL`, `CADDY_ADDRESS`, and `ACME_EMAIL`.
3. Start:

```bash
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml up -d
```

4. Verify all services are running:

```bash
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml ps
```

All containers should show `Up` status. The `migrate` container will exit after completing database migrations (this is expected).

## Accessing the Application

Once all containers are running:

- **Web UI**: Open your browser and navigate to `http://localhost:8080` (or whatever `HTTP_PORT` you configured in `.env`)
- **Backend API**: Internal only at `http://backend:8000` within the Docker network; proxied through Caddy for external access
- **MCP Server**: Available at `http://localhost:8001` (if enabled)

**First Time Setup**:
1. The app will prompt you to create an account or log in.
2. Follow the authentication flow to set up your profile.
3. Start importing transactions or connecting your accounts.

## Local Build From Current Checkout (Dev/QA)

Use this when you want containers to run your current local code (instead of GHCR prebuilt images):

```bash
docker compose \
  --env-file deploy/compose/.env \
  -f deploy/compose/docker-compose.yml \
  -f deploy/compose/docker-compose.local.yml \
  up -d --build
```

This is the recommended flow when validating recent code changes.

## Reusing Existing Dev `.env` Files (Optional)

If you're running this stack from the repo and you already have local dev env files like:

- `backend/.env`
- `frontend/.env.local`

…you can **layer** them into Compose using multiple `--env-file` flags.

Tip: put `deploy/compose/.env` **last** so the Docker-friendly values (like `DATABASE_URL=...@postgres:5432/...`) win over any localhost URLs.

Example (local build):

```bash
docker compose \
  --env-file backend/.env \
  --env-file frontend/.env.local \
  --env-file deploy/compose/.env \
  -f deploy/compose/docker-compose.yml \
  -f deploy/compose/docker-compose.local.yml \
  up -d --build
```

## Notes

- **Only web ports are exposed** by default: `HTTP_PORT` (80) and `HTTPS_PORT` (443).
- DB migrations run automatically via the `migrate` service. They are idempotent.
- File uploads and CSV imports are stored in `public/uploads` and persisted via the `uploads_data` Docker volume.
- This bundle defaults to **Postgres 16**. If you have an existing local Docker volume created by **Postgres 15**, you must dump/restore to upgrade (or temporarily set `POSTGRES_IMAGE=postgres:15-alpine` to keep running on 15).
- We set explicit `container_name` values to avoid the `*-1` suffix. This makes container names stable, but it also means you **cannot** scale services with `--scale`, and you shouldn't run multiple Syllogic stacks on the same Docker host without changing names.

## MCP Server (Enabled By Default)

This bundle includes an **MCP HTTP server** (FastMCP) and starts it by default.

1. Generate an API key in the app UI (Settings -> API Keys).
2. Configure your MCP client to send `Authorization: Bearer pf_...`.
3. Start (or restart) normally:

```bash
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml up -d
```

MCP port contract:
- Internal container port is fixed at `8001`.
- External host port defaults to `8001`.
- Override external port with `MCP_PORT` (example: `MCP_PORT=9001` maps `9001 -> 8001`).

Security note: the MCP service is currently best treated as **single-user** and should only be exposed to trusted networks (LAN/VPN), or protected by an auth layer.

## Making GHCR Images Public

For truly one-click installs, the GHCR packages must be public:

- GitHub → org → Packages → select the image → Package settings → **Change visibility** → Public

## Updating

1. Set `APP_VERSION` in `.env` to the new release tag (e.g. `v1.2.3`).
2. Pull + restart:

```bash
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml pull
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml up -d
```

## One-Command Helpers

From repository root:

- Local infra + migrations for source development: `./scripts/dev-up.sh --local`
- Full prebuilt self-host stack: `./scripts/prod-up.sh`

## Railway Deployment

See [`deploy/railway/`](../railway/) for a Railway-specific compose file and instructions.

## Backups (Docs-Only in v1)

Example manual backup:

```bash
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml exec -T postgres \
  sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup.sql
```
