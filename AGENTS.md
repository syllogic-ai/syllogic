# AGENTS.md

## Cursor Cloud specific instructions

### Architecture overview

Syllogic is a personal wealth management platform with three main services:

| Service | Stack | Port | Purpose |
|---------|-------|------|---------|
| Frontend | Next.js 16+, TypeScript, Drizzle ORM | 3000 | Dashboard, auth, CRUD via Server Actions |
| Backend | FastAPI, Python 3.11+, SQLAlchemy | 8000 | Data enrichment, CSV import, AI categorization |
| Infrastructure | PostgreSQL 16, Redis 7, Celery | 5433, 6379 | Database, cache, background jobs |

Both frontend and backend share a single PostgreSQL database. The frontend (Drizzle) is the schema source of truth.

### Starting services

Infrastructure (Postgres + Redis + Celery) runs in Docker via `docker compose -f docker-compose.yml up -d`. See `scripts/dev-up.sh --local` for the full dev bootstrap sequence.

- **Frontend**: `cd frontend && pnpm dev` (port 3000)
- **Backend**: `cd backend && source venv/bin/activate && uvicorn app.main:app --reload --port 8000`
- **DB migrations**: `cd frontend && DATABASE_URL=postgresql://financeuser:financepass@localhost:5433/finance_db pnpm db:migrate`

### Key gotchas

- **INTERNAL_AUTH_SECRET must match** between `frontend/.env.local` and `backend/.env` (or the backend's environment). Mismatched secrets cause 401 errors when the frontend calls backend endpoints (e.g., transaction import). The `dev-up.sh` script propagates this from `deploy/compose/.env`, but when running services manually, ensure both share the same value.
- **Docker daemon** must be running before `docker compose up`. In Cloud Agent VMs, start it with `sudo dockerd &>/tmp/dockerd.log &` and ensure socket permissions with `sudo chmod 666 /var/run/docker.sock`.
- **esbuild build scripts** are blocked by pnpm's default policy. This produces a warning during `pnpm install` but does not break `drizzle-kit` or other tooling (esbuild falls back to WASM).
- The backend `.env` uses SQLAlchemy-style connection strings (`postgresql+psycopg://...`) while the frontend `.env.local` uses standard Postgres URLs (`postgresql://...`). Both point to the same database on port 5433.

### Lint, test, build

- **Lint**: `cd frontend && pnpm lint` (ESLint)
- **Tests**: `cd frontend && pnpm vitest run` (8 test files, 33 tests)
- **Build**: `cd frontend && pnpm build`
- **Backend tests**: Require running backend server; see `backend/tests/README.md` for details.
