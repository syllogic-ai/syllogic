# Authoring & Publishing the Syllogic Railway Template

This guide is for **maintainers** publishing the official Syllogic template to the
Railway marketplace. Consumers who just want to deploy should use the one-click
button in [`README.md`](README.md).

The design goal is **one place for configuration**: a deployer should be able to
configure (or accept the auto-generated defaults for) a single set of **Shared
Variables**, and every service resolves what it needs from that scope via
`${{shared.VAR}}` references. No service requires its own bootstrap variables.

> **Verified on Railway:** this exact 7-service wiring (shared variables + cross-service
> `${{service.RAILWAY_PRIVATE_DOMAIN}}` references + `${{app.RAILWAY_STATIC_URL}}` +
> volumes + `PROCESS_TYPE` role dispatch) was deployed end-to-end into a throwaway Railway
> project. All services reached `SUCCESS`; the public app served `/api/health`→`200`
> through private networking to the backend, and worker/beat/mcp booted their correct
> roles from `PROCESS_TYPE` alone. The throwaway project was then deleted.

---

## 1. The variable model

Railway has three relevant scopes:

| Scope | Syntax | Used here for |
|---|---|---|
| **Shared** (project/environment) | `${{shared.VAR}}` | The single source of truth for all secrets and optional API keys. |
| **Service reference** | `${{service.VAR}}` | Derived values wired between services (DB URL, Redis URL, app/backend URLs). Maintainer-defined, never touched by the deployer. |
| **Service-local** | `VAR` | Hardcoded ports / runtime flags baked into the template. |

**Rule:** every value a deployer might reasonably want to set lives in **shared**.
Everything else is derived from service references so it cannot drift.

### Auto-generated secrets

Railway template variables support generator functions that run **once** at deploy
time ([docs](https://docs.railway.com/reference/templates)):

- `${{secret(length?, alphabet?)}}` — random secret (default 32 chars, default alphabet).
- `${{randomInt(min?, max?)}}` — random integer.

Because each shared variable is generated **once** and then referenced everywhere,
secrets that must match across services (the DB password, the internal HMAC secret,
the encryption key) stay consistent automatically. **Do not** inline `${{secret()}}`
directly into individual service variables — that would generate a *different* value
per service and break Postgres auth, internal auth, and decryption.

---

## 2. Shared variable contract (the "one place")

Set these as **Shared Variables** in the template composer. The "Default value"
column is what to paste into the composer so the value is generated for the deployer
— they normally don't need to change anything except the optional keys.

| Variable | Class | Default value to set in composer | Description (paste into the composer's description field) |
|---|---|---|---|
| `POSTGRES_PASSWORD` | Auto-generated | `${{secret(32, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")}}` | Password for the bundled PostgreSQL database. Alphanumeric so it is safe inside `DATABASE_URL`. Auto-generated — leave as-is. |
| `BETTER_AUTH_SECRET` | Auto-generated | `${{secret(48)}}` | Session/auth signing secret for the web app (BetterAuth). Auto-generated — leave as-is. |
| `INTERNAL_AUTH_SECRET` | Auto-generated | `${{secret(48)}}` | Shared HMAC secret signing app→backend `/internal/*` and `/api/*` calls. Must be identical for app, backend, worker, beat — keeping it shared guarantees that. Auto-generated — leave as-is. |
| `DATA_ENCRYPTION_KEY_CURRENT` | Auto-generated | `${{secret(64, "0123456789abcdef")}}` | App-layer field-encryption key. 64 hex chars = exactly 32 bytes, which is what the app requires. Auto-generated — leave as-is. |
| `DATA_ENCRYPTION_KEY_ID` | Static | `k1` | Identifier embedded in encrypted payloads. Bump to `k2`, `k3`, … only when rotating keys. |
| `DATA_ENCRYPTION_KEY_PREVIOUS` | Optional | *(empty)* | Previous encryption key, set only during a key-rotation window so old data still decrypts. Leave empty otherwise. |
| `OPENAI_API_KEY` | Optional | *(empty)* | Enables AI transaction categorization (GPT-4o-mini). If empty, the app falls back to keyword matching. |
| `LOGO_DEV_API_KEY` | Optional | *(empty)* | Enables merchant/company logo lookup via logo.dev. If empty, logos are silently disabled. |
| `MCP_SERVER_URL` | Optional | *(empty)* | Overrides the MCP URL shown in the app's Claude Desktop snippet. If empty, derived from the app URL at runtime. |

> Net result for a deployer: a working install with **zero required inputs**.
> The optional API keys are the only fields they might fill in.

---

## 3. Service topology

Seven services, all reading secrets from `shared.*`. Derived URLs use service
references so they self-wire on Railway's private network.

| Service | Image / source | Public? | Volume | Notes |
|---|---|---|---|---|
| `postgres` | `ghcr.io/railwayapp-templates/postgres-ssl:16` | Private | `/var/lib/postgresql/data` | **SSL-enabled** Postgres. The backend enforces TLS on `DATABASE_URL` for non-local hosts in production, so `sslmode=require` only works against an SSL-capable server — plain `postgres:16-alpine` (ssl=off) would reject it. Initialized with `POSTGRES_PASSWORD`. |
| `redis` | `redis:7-alpine` | Private | `/data` | Celery broker + cache. |
| `backend` | `ghcr.io/syllogic-ai/syllogic-backend` | Private | — | FastAPI API (default role, `PROCESS_TYPE` unset), healthcheck `/health`. |
| `worker` | same backend image | Private | — | Celery worker. Set `PROCESS_TYPE=worker`. |
| `beat` | same backend image | Private | — | Celery beat scheduler. Set `PROCESS_TYPE=beat`. |
| `mcp` | same backend image | Optional public (TCP 8001) | — | FastMCP server. Set `PROCESS_TYPE=mcp` + `PORT=8001`, healthcheck `/health`. |
| `app` | `ghcr.io/syllogic-ai/syllogic-frontend` | **Public (HTTP)** | `/data/uploads` | Next.js. Image CMD runs `node scripts/migrate.js` before start. `LOCAL_STORAGE_PATH=/data/uploads`. |

> **Role selection without start commands:** the backend image's entrypoint dispatches
> on `PROCESS_TYPE` (`worker`→celery worker, `beat`→celery beat, `mcp`→uvicorn, unset→gunicorn API).
> So `backend`/`worker`/`beat`/`mcp` all use the **same image with no custom start command** —
> you only set a `PROCESS_TYPE` env var. This is the recommended approach for image/dashboard
> templates (Railway doesn't always preserve compose `command:` overrides on import).

### Derived (reference) variables — maintainer-set, never deployer-facing

These are configured on the relevant services in the composer, **not** as shared
variables:

> **`?sslmode=require` requires an SSL-capable Postgres.** The backend enforces TLS
> on `DATABASE_URL` for non-local hosts in production, but plain `postgres:16-alpine`
> has `ssl=off` and rejects `sslmode=require` ("server does not support SSL"). That's
> why the `postgres` service uses `ghcr.io/railwayapp-templates/postgres-ssl:16`
> (auto-generated self-signed certs; `sslmode=require` works, `verify-*` would not).

```bash
# On backend / worker / beat / mcp / app (as applicable):
DATABASE_URL=postgresql://financeuser:${{shared.POSTGRES_PASSWORD}}@${{postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/finance_db?sslmode=require
REDIS_URL=redis://${{redis.RAILWAY_PRIVATE_DOMAIN}}:6379/0

# On app:
BACKEND_URL=http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:${{backend.PORT}}
APP_URL=${{app.RAILWAY_STATIC_URL}}
BETTER_AUTH_URL=${{app.RAILWAY_STATIC_URL}}
NEXT_PUBLIC_BETTER_AUTH_URL=${{app.RAILWAY_STATIC_URL}}

# On backend / worker / beat:
FRONTEND_URL=${{app.RAILWAY_STATIC_URL}}
CORS_ALLOW_ORIGINS=${{app.RAILWAY_STATIC_URL}}
```

The committed [`docker-compose.yml`](docker-compose.yml) in this directory is the
canonical wiring for all of the above. Use it as the reference when filling in the
composer, or import it as a starting point (see below).

---

## 4. Publishing the template (dashboard)

Railway templates are created and published from the dashboard; there is no
repo-committed file that Railway auto-ingests. The committed compose + this guide
are the source of truth you transcribe into the composer.

**Recommended: generate from a working project.**

1. Stand up a project from [`docker-compose.yml`](docker-compose.yml) (drag it onto
   the canvas) and confirm it runs end-to-end with the variable contract above.
2. Open the project → **Settings** → scroll to **Generate Template from Project** →
   **Create Template**.
3. In the **template composer**, for each service:
   - **Variables tab:** confirm the shared references resolve. For each shared
     variable, set the **default value** and **description** from the table in §2.
     Prefer reference variables (`${{shared.*}}`, `${{service.*}}`) over literals —
     Railway rewards this with a higher-quality template badge.
   - **Settings tab:** set start command, healthcheck path, and root directory
     (only relevant for the source/v2 variant; see §6).
   - **Volumes:** right-click the service → **Attach Volume** with the mount path
     from the topology table (`app` → `/data/uploads`, `postgres` →
     `/var/lib/postgresql/data`, `redis` → `/data`).
4. Enable **public networking** on `app` only (HTTP). Leave everything else private.
   Optionally expose `mcp` over a TCP proxy on `8001`.
5. **Create Template**, then **Publish** it. (A template is not on the marketplace —
   and not eligible for kickbacks — until published.)
6. Copy the generated deploy URL and update the button in [`README.md`](README.md)
   and the repo root `README.md` / `START_HERE.md`.

---

## 5. Verification checklist before publishing

- [ ] Deploy the template into a fresh project accepting **all defaults** (no inputs).
- [ ] All seven services reach a running/healthy state.
- [ ] `app` is the only HTTP-public service; the rest are private.
- [ ] Volumes attached: `app`→`/data/uploads`, `postgres`→`/var/lib/postgresql/data`, `redis`→`/data`.
- [ ] Sign-up works (proves migrations ran and `DATABASE_URL`/`INTERNAL_AUTH_SECRET` match).
- [ ] Upload a profile photo, redeploy `app`, confirm it still renders (proves the volume persists).
- [ ] `mcp` `GET /health` returns `200`.
- [ ] Set `OPENAI_API_KEY` empty → app still boots and categorizes via keyword fallback.

---

## 6. Image (v1) vs. source (v2) variants

This template ships in two channels — see [`README.md`](README.md) and
[`V1_TO_V2_MIGRATION.md`](V1_TO_V2_MIGRATION.md):

- **v1 (image):** services use pinned `ghcr.io/syllogic-ai/*` tags. Fast, no build.
  Pin `vX.Y.Z` tags before publishing — never ship `edge`.
- **v2 (source):** services build from this GitHub repo using the `railway.toml`
  files (`frontend/railway.toml`, `backend/railway.*.toml`). Use Railway's managed
  Postgres/Redis plugins and wire `DATABASE_URL`/`REDIS_URL` from the plugin
  references instead of the bundled `postgres`/`redis` services.

The shared-variable contract in §2 is **identical** for both channels.
