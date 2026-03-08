# Agents

## Cursor Cloud specific instructions

### Overview

Syllogic is a personal finance app with three components:
- **Frontend** (`frontend/`): Next.js 16 + TypeScript + Drizzle ORM — port 3000
- **Backend** (`backend/`): FastAPI + SQLAlchemy + Celery — port 8000
- **Infrastructure**: PostgreSQL (port 5433) + Redis (port 6379) via Docker Compose

### Starting services

1. **Docker daemon**: `sudo dockerd &>/tmp/dockerd.log &` then `sudo chmod 666 /var/run/docker.sock`
2. **PostgreSQL + Redis**: `docker compose -f docker-compose.yml up -d db redis` from repo root
3. **Frontend**: `cd frontend && pnpm dev` (port 3000)
4. **Backend**: `cd backend && source venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` — requires env vars `DATABASE_URL`, `REDIS_URL`, `APP_URL`, `INTERNAL_AUTH_SECRET` (see `backend/.env`)
5. **DB migrations**: `cd frontend && DATABASE_URL="postgresql://financeuser:financepass@localhost:5433/finance_db" pnpm db:migrate`

### Lint / Test / Build

- **Frontend lint**: `cd frontend && pnpm lint` (ESLint; 0 errors expected, warnings are acceptable)
- **Frontend tests**: `cd frontend && pnpm vitest run` (8 test files, 33 tests)
- **Frontend build**: `cd frontend && pnpm build`
- **Backend tests**: Require running backend server; see `backend/tests/README.md`

### Agentic import feature

The AI-powered import (`/transactions/import`) requires `OPENAI_API_KEY` in both frontend (`.env.local`) and backend (`.env` or env var). Without it, the import page shows a disabled state. The feature uses:
- Backend endpoints at `/api/agentic-import/` (upload, analyze, approve, profiles)
- Script sandbox: subprocess execution with AST validation for security
- Format profiles: per-user, keyed by SHA-256 of sorted column headers

### Non-obvious caveats

- The root `docker-compose.yml` is for local dev infra only (db + redis + optional celery workers). Production uses `deploy/compose/docker-compose.yml`.
- Frontend acts as a reverse proxy to the backend — all `/api/*` requests go through Next.js, which signs them with HMAC (`INTERNAL_AUTH_SECRET`). Both frontend and backend must share the same `INTERNAL_AUTH_SECRET`.
- `pnpm install` may warn about ignored build scripts for `esbuild` and `msw`. This is expected and does not affect functionality.
- The backend venv is at `backend/venv/` — always activate it before running backend commands.
- Env files: `frontend/.env.local` and `backend/.env` are not committed. The `deploy/compose/.env` holds shared secrets used to generate both.
- The account dropdown in the "Add Transaction" dialog may show UUIDs instead of names — this is a known UI quirk in development.
