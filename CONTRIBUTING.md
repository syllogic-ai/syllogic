# Contributing to Syllogic

Thanks for your interest in contributing. This guide covers how to set up a development environment and submit changes.

## Prerequisites

- Docker and Docker Compose
- Node.js 18+ and pnpm
- Python 3.11+

## Development Setup

### 1. Start Infrastructure

The quickest way to get a development environment running:

```bash
./scripts/dev-up.sh --local
```

This starts PostgreSQL (port 5433) and Redis (port 6379) in Docker and runs database migrations.

### 2. Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your configuration
```

Start the API server:

```bash
uvicorn app.main:app --reload
```

Start background workers (separate terminals):

```bash
celery -A celery_app worker --loglevel=info
celery -A celery_app beat --loglevel=info
```

### 3. Frontend

```bash
cd frontend
pnpm install
cp .env.example .env.local
# Edit .env.local with your configuration
pnpm dev
```

App available at http://localhost:3000.

### Local Full-Stack Docker

To test the full containerized stack with your local code:

```bash
cp deploy/compose/.env.example deploy/compose/.env
# Edit deploy/compose/.env
docker compose \
  --env-file deploy/compose/.env \
  -f deploy/compose/docker-compose.yml \
  -f deploy/compose/docker-compose.local.yml \
  up -d --build
```

## Database Management

```bash
cd frontend
pnpm db:push       # Push schema changes to database
pnpm db:generate   # Generate migration files
pnpm db:studio     # Open Drizzle Studio (database GUI)
```

Schema changes must be made in Drizzle first (source of truth), then mirrored to SQLAlchemy models in the backend.

## Code Style

### Frontend

- TypeScript strict mode
- Server Actions for all data mutations
- shadcn/ui components before building custom UI
- Follow the existing folder structure and naming conventions

### Backend

- PEP 8 style guide
- Type hints where practical

## Submitting Changes

1. Fork the repository and create a feature branch
2. Make your changes following the style guidelines above
3. Test your changes thoroughly
4. Update documentation if you're changing functionality
5. Submit a pull request with a clear description of changes

## Reporting Issues

Use GitHub Issues to report bugs or request features. Include:

- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Screenshots if applicable
- Environment details (OS, browser, etc.)
