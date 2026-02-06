# Self-Hosted (Production) Docker Compose

This directory contains the production-grade Docker Compose bundle:

- PostgreSQL 16
- Redis 7
- FastAPI backend + Celery worker/beat
- Next.js frontend
- Caddy reverse proxy (TLS by default)
- One-shot Drizzle migration job (runs on deploy/boot)

## Quick Start

1. Copy `deploy/compose/.env.example` to `deploy/compose/.env`.
2. Edit `.env` values (at minimum: `POSTGRES_PASSWORD`, `APP_URL`, `CADDY_ADDRESS`, `ACME_EMAIL`).
3. Start:

```bash
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml up -d
```

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

## Optional: MCP Server (Claude Desktop / Programmatic Access)

This bundle includes an optional **MCP HTTP server** (FastMCP). It's disabled by default and only starts when you enable the `mcp` profile.

1. Generate an API key in the app UI (Settings -> API Keys).
2. Add it to `.env` as `PERSONAL_FINANCE_API_KEY=pf_...`.
3. Start (or restart) with the profile enabled:

```bash
docker compose --profile mcp --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml up -d
```

By default it binds to host port `8001` (override with `MCP_PORT`).

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

## Backups (Docs-Only in v1)

Example manual backup:

```bash
docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.yml exec -T postgres \
  sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup.sql
```
