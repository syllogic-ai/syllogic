![Syllogic](https://pub-9a7afb92aeda47c8a8856a83903f29d1.r2.dev/syllogic/syllogic/syllogic-finance-banner.png)

<p align="center">
  <h1 align="center"><b>Syllogic</b></h1>
  <p align="center">
    An open-source, minimal, wealth management app
    <br />
    <br />
    <a href="https://github.com/syllogic-ai/personal-finance-app">GitHub</a>
    ·
    <a href="https://github.com/syllogic-ai/personal-finance-app/issues">Issues</a>
    ·
    <a href="#railway-one-click">Deploy</a>
  </p>
</p>

<p align="center">
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License" />
  </a>
  <a href="https://github.com/orgs/syllogic-ai/packages">
    <img src="https://img.shields.io/badge/Docker-GHCR-blue?logo=docker" alt="Docker" />
  </a>
  <a href="https://railway.com/deploy/N98lwA?referralCode=25KFsK&utm_medium=integration&utm_source=template&utm_campaign=generic">
    <img src="https://img.shields.io/badge/Deploy-Railway-blueviolet?logo=railway" alt="Deploy on Railway" />
  </a>
</p>

## About Syllogic

Syllogic is an open-source wealth management platform that gives you a complete picture of your finances — balances, spending, subscriptions, and trends — all in one place. Connect your bank accounts, let AI handle categorization, and keep your data on your own infrastructure.

## Features

**Financial Dashboard** — real-time balances, spending patterns, and financial health overview.<br/>
**AI Categorization** — automatic transaction categorization and merchant enrichment via OpenAI.<br/>
**Subscription Tracking** — monitor recurring payments with company logo integration.<br/>
**Category Analytics** — interactive charts and spending breakdowns.<br/>
**Transaction Linking** — link transactions with reimbursements for bill splitting.<br/>
**CSV Import/Export** — bulk import and export transaction data.<br/>

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
- `DATA_ENCRYPTION_KEY_CURRENT` (recommended — field-level encryption)
- `DATA_ENCRYPTION_KEY_ID` (recommended — e.g. `k1`)
- `OPENAI_API_KEY` (optional — enables AI categorization)
- `LOGO_DEV_API_KEY` (optional — enables company logos)

For full Railway setup details, see [`deploy/railway/README.md`](deploy/railway/README.md).

### Other Deployment Methods

| Method | Use case | Docs |
|--------|----------|------|
| CasaOS | Home lab / NAS users | [`deploy/casaos/`](deploy/casaos/README.md) |

## Configuration

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

- Next.js 16+ (TypeScript, Drizzle ORM, BetterAuth, shadcn/ui, Recharts)
- FastAPI (SQLAlchemy 2.0, Celery + Redis, OpenAI)
- PostgreSQL 16, Redis 7, Docker Compose

Both services share a single PostgreSQL database. The frontend handles all CRUD via Server Actions; the backend handles data enrichment, bank sync, and background jobs.

## Development

Quick start for contributors:

```bash
git clone https://github.com/syllogic-ai/personal-finance-app.git
cd personal-finance-app
./scripts/dev-up.sh --local
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full setup instructions and code style guidelines.

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).
