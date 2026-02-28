# Syllogic

> Open-source personal finance platform with AI-powered categorization and bank sync.

[![License: LGPL-3.0-or-later](https://img.shields.io/badge/License-LGPL--3.0--or--later-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-GHCR-blue?logo=docker)](https://github.com/orgs/syllogic-ai/packages)
[![Deploy on Railway](https://img.shields.io/badge/Deploy-Railway-blueviolet?logo=railway)](https://railway.com/deploy/N98lwA?referralCode=25KFsK&utm_medium=integration&utm_source=template&utm_campaign=generic)

[Self-Host](#self-hosted-docker) · [Deploy to Railway](#railway-one-click) · [Contributing](CONTRIBUTING.md)

<!-- TODO: Add screenshot of dashboard -->

---

## Features

- **Financial Dashboard** — real-time balances, spending patterns, and financial health overview
- **AI Categorization** — automatic transaction categorization and merchant enrichment via OpenAI
- **Bank Sync** — connect your bank accounts for automated transaction import
- **Subscription Tracking** — monitor recurring payments with company logo integration
- **Category Analytics** — interactive charts and spending breakdowns
- **Transaction Linking** — link transactions with reimbursements for bill splitting
- **CSV Import/Export** — bulk import and export transaction data
- **Dark Mode** — full dark mode support

## Quick Start

### Self-Hosted (Docker)

**One-liner** (requires root, Docker, and Docker Compose):

```bash
curl -fsSL https://github.com/syllogic-ai/personal-finance-app/releases/download/v1.0.0/install.sh | sudo bash -s -- v1.0.0
```

**Or manually:**

1. Clone and configure:
   ```bash
   git clone https://github.com/syllogic-ai/personal-finance-app.git
   cd personal-finance-app
   cp deploy/compose/.env.example deploy/compose/.env
   # Edit deploy/compose/.env — set POSTGRES_PASSWORD, BETTER_AUTH_SECRET, INTERNAL_AUTH_SECRET
   ```

2. Start:
   ```bash
   ./scripts/prod-up.sh
   ```

3. Open `http://localhost:8080` and create your account.

For advanced configuration (TLS, custom domains, MCP server), see [`deploy/compose/README.md`](deploy/compose/README.md).

### Railway (One-Click)

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/N98lwA?referralCode=25KFsK&utm_medium=integration&utm_source=template&utm_campaign=generic)

After deploy, set these **Shared Variables** in Railway:

- `POSTGRES_PASSWORD` (required)
- `BETTER_AUTH_SECRET` (required)
- `INTERNAL_AUTH_SECRET` (required)
- `OPENAI_API_KEY` (optional — enables AI categorization)
- `LOGO_DEV_API_KEY` (optional — enables company logos)

For full Railway setup details, see [`deploy/railway/README.md`](deploy/railway/README.md).

### Other Deployment Methods

| Method | Use case | Docs |
|--------|----------|------|
| CasaOS | Home lab / NAS users | [`deploy/casaos/`](deploy/casaos/README.md) |

## Configuration

### Essential Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `POSTGRES_PASSWORD` | PostgreSQL password | Yes |
| `BETTER_AUTH_SECRET` | Auth session signing key | Yes |
| `INTERNAL_AUTH_SECRET` | App-to-backend signed auth | Yes |
| `DATA_ENCRYPTION_KEY_CURRENT` | Field-level encryption key | Recommended |
| `OPENAI_API_KEY` | AI transaction categorization | No |
| `LOGO_DEV_API_KEY` | Company logo lookup | No |

Generate secrets with `openssl rand -hex 32`. For encryption keys: `openssl rand -base64 32`.

Full variable reference is available in [`deploy/compose/.env.example`](deploy/compose/.env.example).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Next.js)                                         │
│  - Server Actions + Drizzle ORM (all CRUD)                  │
│  - BetterAuth (authentication)                              │
│  - shadcn/ui + Recharts (UI/charts)                         │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────▼───────────┐
              │  PostgreSQL (shared)  │
              └───────────┬───────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│  Backend (Python/FastAPI)                                   │
│  - Open banking + data integrations                         │
│  - Transaction enrichment & categorization                  │
│  - Celery + Redis (cron jobs)                               │
└─────────────────────────────────────────────────────────────┘
```

### Tech Stack

**Frontend:** Next.js 16+, TypeScript, Drizzle ORM, BetterAuth, shadcn/ui, Recharts, TanStack Query

**Backend:** FastAPI, SQLAlchemy 2.0, Celery + Redis, OpenAI

**Infrastructure:** PostgreSQL 16, Redis 7, Docker Compose

## Development

For local development, see the [Contributing Guide](CONTRIBUTING.md).

Quick start for contributors:

```bash
git clone https://github.com/syllogic-ai/personal-finance-app.git
cd personal-finance-app
./scripts/dev-up.sh --local
```

This starts PostgreSQL and Redis in Docker, runs migrations, and leaves you ready to start the frontend and backend from source.

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, code style guidelines, and PR process.

## License

Licensed under the [GNU Lesser General Public License v3.0 or later](LICENSE) (LGPL-3.0-or-later).
