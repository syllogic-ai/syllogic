# Deployment Matrix and Environment Contract

This document defines the supported deployment surfaces and a shared environment-variable contract.

## Deployment Surfaces

| Surface | Primary use | Service model | Data services | Artifact strategy |
|---|---|---|---|---|
| `local` | Day-to-day development | Source workflow + local infra containers | Local Postgres/Redis containers | Local source checkout |
| `self-host` | VPS / one-click install | Docker Compose (image-based) | Bundled Postgres/Redis containers | Pinned release tags (`vX.Y.Z`) |
| `railway-v1` | Existing template installs | Railway compose template (image-based) | Template Postgres/Redis or plugins | Pinned release tags (`vX.Y.Z`) |
| `railway-v2` | New template installs | Railway GitHub-source services | Railway Postgres/Redis plugins | GitHub source builds from `main` |

## Image Channel Policy

1. `edge`: development/testing only.
2. `vX.Y.Z`: production, self-hosted one-click, and published templates.
3. Do not run internet-facing production on `edge`.

## Environment Contract

The table below is the canonical contract. Keep all deploy docs aligned with it.

| Variable | Class | Scope | Notes |
|---|---|---|---|
| `POSTGRES_PASSWORD` | Required | self-host, railway-v1 | Required for containerized Postgres init. |
| `BETTER_AUTH_SECRET` | Required | all except local infra-only | Session/auth signing secret. |
| `INTERNAL_AUTH_SECRET` | Required | all | Internal signed app->backend calls. |
| `DATABASE_URL` | Required | all | Must use TLS in production-like external DB paths (`sslmode=require` or stricter). |
| `REDIS_URL` | Required | backend/worker/beat surfaces | Queue/cache transport URL. |
| `APP_URL` | Required | app-serving surfaces | Public app base URL. |
| `BACKEND_URL` | Required | app runtime | Internal/backend URL for app API calls. |
| `DATA_ENCRYPTION_KEY_CURRENT` | Prod-only required (recommended everywhere) | all production surfaces | App-layer field encryption key. |
| `DATA_ENCRYPTION_KEY_ID` | Prod-only required (recommended everywhere) | all production surfaces | Key identifier (`k1`, `k2`, ...). |
| `DATA_ENCRYPTION_KEY_PREVIOUS` | Optional | production surfaces | Decrypt fallback during rotation window. |
| `OPENAI_API_KEY` | Optional | all | Enables AI categorization. |
| `LOGO_DEV_API_KEY` | Optional | app surfaces | Enables logo lookup/cache enrichment. |
| `ACME_EMAIL` | Prod-only required (public self-host TLS) | self-host | Required when using domain-based automatic certs. |
| `CADDY_ADDRESS` | Required | self-host | Domain for TLS or `:80` in LAN/dev mode. |
| `NEXT_DISABLE_TURBOPACK` | Dev-only optional | local/self-host build workflows | Build toggle for troubleshooting local builds. |
| `MCP_PORT` | Dev-only optional | local/LAN self-host | Host mapping override for MCP external port. |

## Encryption Expectations by Surface

1. `local`: encryption keys optional, but local smoke should validate encryption helpers.
2. `self-host`: encryption keys strongly recommended by default; run upgrade script on existing data.
3. `railway-v1`: set encryption keys in shared variables; run upgrade script after rollout.
4. `railway-v2`: same as v1; source-service model does not change encryption contract.

Upgrade command for existing data:

```bash
python postgres_migration/run_encryption_upgrade.py --batch-size 500
```

Optional:

```bash
python postgres_migration/run_encryption_upgrade.py --batch-size 500 --dry-run
python postgres_migration/run_encryption_upgrade.py --batch-size 500 --clear-plaintext
```
