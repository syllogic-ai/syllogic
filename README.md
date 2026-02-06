# Syllogic

Syllogic is a modern, full-stack personal finance management platform for tracking savings, expenses, investments, and subscriptions with automated bank synchronization.

## What it does

This application helps you take control of your personal finances by providing:

- **Financial Dashboard**: Real-time overview of your balances, spending patterns, and financial health
- **Smart Categorization**: AI-powered transaction categorization and enrichment using OpenAI
- **Transaction Management**: View, filter, search, and manually categorize transactions
- **Subscription Tracking**: Monitor recurring payments and subscriptions with company logo integration (Logo.dev API)
- **Category Analytics**: Visualize spending patterns by category with interactive charts
- **Scheduled Tasks**: Automated data refresh and synchronization via background jobs
- **Transaction Linking**: Link transactions with reimbusments that will help you split the bill, when f.i. you pay for the whole table!

## Why it exists

Managing personal finances across multiple accounts and tracking spending patterns can be overwhelming. This app was built to:

- **Automate the tedious**: No more manual transaction entry - connect your bank and let the app do the work
- **Gain insights**: Understand where your money goes with visual breakdowns and analytics
- **Stay organized**: Keep all your financial data in one place with smart categorization
- **Make better decisions**: Use data-driven insights to improve your financial health

## Features

### Core Functionality
- Dashboard with balance overview and recent transactions
- Transaction list with advanced filtering, search, and pagination
- Category management for expenses and income
- Multi-account support with connected accounts view
- CSV import/export for transaction data
- Dark mode support

### Data Pipeline
- AI-powered transaction enrichment and merchant identification
- Automatic categorization based on transaction patterns
- Background job processing with Celery + Redis
- Scheduled daily syncs and data refresh

### Analytics & Insights
- Spending breakdown by category
- Subscription KPIs and recurring payment tracking
- Category share visualization
- Time-based spending trends

## Architecture

The app uses a **two-service architecture** with a shared PostgreSQL database:

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
│  - GoCardless integration (bank sync)                       │
│  - Transaction enrichment & categorization                  │
│  - Celery + Redis (cron jobs)                               │
└─────────────────────────────────────────────────────────────┘
```

### Tech Stack

**Frontend:**
- Next.js 16+ with App Router and Server Components
- TypeScript (strict mode)
- Drizzle ORM for database operations
- BetterAuth for authentication
- shadcn/ui (Lyra style) + Remix Icons
- TanStack Query for server state
- Recharts for data visualization
- React Hook Form + Zod for forms and validation

**Backend:**
- FastAPI for API endpoints
- SQLAlchemy 2.0 as ORM
- Celery + Redis for background jobs
- GoCardless/Nordigen for bank sync
- OpenAI for transaction enrichment

**Infrastructure:**
- PostgreSQL 15
- Redis 7
- Docker & Docker Compose

## Installation

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ and pnpm
- Python 3.11+
- OpenAI API key (optional, for AI categorization)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/personal-finance-app.git
cd personal-finance-app
```

### 2. Start Infrastructure Services

```bash
docker-compose up -d db redis
```

This starts PostgreSQL (port 5433) and Redis (port 6379).

### 3. Setup Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your database URL and API keys
```

**Backend `.env` configuration:**
```env
DATABASE_URL=postgresql+psycopg://financeuser:financepass@localhost:5433/finance_db
REDIS_URL=redis://localhost:6379/0
GOCARDLESS_SECRET_ID=your-gocardless-id
GOCARDLESS_SECRET_KEY=your-gocardless-key
OPENAI_API_KEY=your-openai-key
```

### 4. Setup Frontend

```bash
cd frontend

# Install dependencies
pnpm install

# Create .env.local file
cp .env.example .env.local
# Edit .env.local with your configuration
```

**Frontend `.env.local` configuration:**
```env
DATABASE_URL=postgresql://financeuser:financepass@localhost:5433/finance_db
BETTER_AUTH_SECRET=your-secret-key-here
BETTER_AUTH_URL=http://localhost:3000
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

### 5. Initialize Database

```bash
cd frontend
pnpm db:push
```

Optionally seed with sample data:
```bash
cd backend
python seed_data.py
```

## Usage

### Development Mode

**Start all services with Docker Compose:**
```bash
docker-compose up
```

This starts:
- PostgreSQL database (port 5433)
- Redis (port 6379)
- Celery worker (background jobs)
- Celery beat (scheduled tasks)

**Or run services individually:**

1. **Backend API:**
```bash
cd backend
source venv/bin/activate  # or venv\Scripts\activate on Windows
uvicorn app.main:app --reload
```
API available at: http://localhost:8000
API docs at: http://localhost:8000/docs

2. **Celery Worker (background jobs):**
```bash
cd backend
celery -A celery_app worker --loglevel=info
```

3. **Celery Beat (scheduled tasks):**
```bash
cd backend
celery -A celery_app beat --loglevel=info
```

4. **Frontend:**
```bash
cd frontend
pnpm dev
```
App available at: http://localhost:3000

### Production Build

**Frontend:**
```bash
cd frontend
pnpm build
pnpm start
```

**Backend:**
```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Database Management

```bash
cd frontend

# Push schema changes to database
pnpm db:push

# Generate migration files
pnpm db:generate

# Open Drizzle Studio (database GUI)
pnpm db:studio
```

## Configuration

### Environment Variables

#### Frontend (.env.local)
| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `BETTER_AUTH_SECRET` | Secret key for authentication | Yes |
| `BETTER_AUTH_URL` | App URL for auth callbacks | Yes |
| `NEXT_PUBLIC_APP_URL` | Public app URL | Yes |

#### Backend (.env)
| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `GOCARDLESS_SECRET_ID` | GoCardless API ID | No |
| `GOCARDLESS_SECRET_KEY` | GoCardless API key | No |
| `OPENAI_API_KEY` | OpenAI API key | No |
| `LOGO_DEV_API_KEY` | Logo.dev API key | No |

### Docker Compose Configuration

The `docker-compose.yml` file configures:
- PostgreSQL with optimized settings for performance
- Redis with persistence
- Celery worker with 4 concurrent workers
- Celery beat for scheduled tasks

Modify `docker-compose.yml` to adjust:
- Database connection settings
- Redis configuration
- Celery concurrency
- Volume mounts

## Project Structure

```
personal-finance-app/
├── frontend/
│   ├── app/
│   │   ├── (auth)/              # Login/register pages
│   │   ├── (dashboard)/         # Main app pages
│   │   │   ├── page.tsx         # Dashboard
│   │   │   ├── transactions/    # Transaction pages
│   │   │   └── settings/        # Settings pages
│   │   └── api/auth/[...all]/   # BetterAuth handler
│   ├── components/
│   │   ├── ui/                  # shadcn components
│   │   ├── layout/              # Layout components
│   │   └── charts/              # Chart components
│   ├── lib/
│   │   ├── db/                  # Drizzle client & schema
│   │   ├── auth.ts              # BetterAuth config
│   │   └── actions/             # Server Actions
│   └── drizzle.config.ts
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── database.py          # Database config
│   │   ├── models.py            # SQLAlchemy models
│   │   └── routes/              # API routes
│   ├── celery_app.py            # Celery configuration
│   ├── tasks/                   # Celery tasks
│   └── seed_data.py             # Sample data generator
├── docs/
│   └── architecture.md          # Detailed architecture docs
├── docker-compose.yml
└── README.md
```

## API Endpoints

### Accounts
- `GET /api/accounts` - List all accounts
- `GET /api/accounts/{id}` - Get account details

### Categories
- `GET /api/categories` - List all categories
- `POST /api/categories` - Create a category
- `PATCH /api/categories/{id}` - Update category
- `DELETE /api/categories/{id}` - Delete category

### Transactions
- `GET /api/transactions` - List transactions (with filters)
- `GET /api/transactions/{id}` - Get transaction details
- `PATCH /api/transactions/{id}/category` - Assign category
- `POST /api/transactions/import` - Import from CSV
- `GET /api/transactions/export` - Export to CSV

### Analytics
- `GET /api/transactions/stats/by-category` - Spending by category
- `GET /api/subscriptions/kpis` - Subscription KPIs
- `GET /api/categories/share` - Category share breakdown

## Contributing

Contributions are welcome! Please follow these guidelines:

1. **Fork the repository** and create a feature branch
2. **Follow the existing code style**:
   - Frontend: Use TypeScript strict mode, follow Next.js best practices
   - Backend: Follow PEP 8 style guide
3. **Write descriptive commit messages**
4. **Test your changes** thoroughly
5. **Update documentation** if you're changing functionality
6. **Submit a pull request** with a clear description of changes

### Development Guidelines

- Use Server Actions for all frontend data mutations
- Database schema changes must be made in Drizzle first, then mirrored to SQLAlchemy
- Use shadcn/ui components before building custom UI
- Follow the existing folder structure and naming conventions
- Add comments for complex logic

### Reporting Issues

Please use GitHub Issues to report bugs or request features. Include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Screenshots if applicable
- Environment details (OS, browser, etc.)

## License

This library is licensed under the GNU Lesser General Public License v3.0
or later (LGPL-3.0-or-later).

See the LICENSE file for details, and COPYING for the GNU GPL v3.

---

Built with Next.js, FastAPI, and PostgreSQL. Powered by GoCardless for bank sync and OpenAI for smart categorization.
