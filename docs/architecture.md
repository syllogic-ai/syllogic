# Personal Finance App - Architecture

## 1. Overview

A personal finance management platform with a **two-service architecture**:

- **Frontend (Next.js)**: User interface, authentication, CRUD operations, analytics queries
- **Backend (Python/FastAPI)**: Data pipeline for transaction enrichment, categorization, and processing

Both services share a single PostgreSQL database, with Drizzle ORM (frontend) as the source of truth for schema migrations.

### Core Value Proposition

Unified financial visibility with intelligent categorization and portfolio tracking across all asset types.

---

## 2. Architecture Diagram

```mermaid
flowchart TB
    subgraph client [Browser]
        Browser[React Client Components]
    end

    subgraph frontend [Next.js Frontend]
        RSC[React Server Components]
        SA[Server Actions]
        Drizzle[Drizzle ORM]
        Auth[BetterAuth]
        API[API Routes]
    end
    
    subgraph backend [Python Backend - Data Pipeline]
        Cron[Cron Jobs / Celery Beat]
        Enrich[Enrichment Service]
        Categorize[Categorization Engine]
        Reconcile[Reconciliation]
        Ingest[Data Ingestion]
        SQLAlchemy[SQLAlchemy ORM]
    end
    
    subgraph infra [Infrastructure - Docker]
        PG[(PostgreSQL 16)]
        Redis[(Redis 7)]
    end
    
    Browser --> RSC
    RSC --> SA
    SA --> Drizzle
    SA --> Auth
    Drizzle --> PG
    Auth --> PG
    API --> Auth
    
    Cron --> Redis
    Cron --> Enrich
    Enrich --> Categorize
    Categorize --> Reconcile
    Reconcile --> Ingest
    Ingest --> SQLAlchemy
    SQLAlchemy --> PG
```

### Service Responsibilities

| Service | Responsibilities |
|---------|------------------|
| **Frontend** | UI rendering, user authentication, CRUD operations (accounts, transactions, categories), analytics queries, data visualization |
| **Backend** | Cron jobs, transaction enrichment, auto-categorization, reconciliation, data processing |

---

## 3. Technology Stack

### 3.1 Frontend Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Framework | Next.js 16+ | App Router, React Server Components |
| Language | TypeScript | Strict mode enabled |
| ORM | Drizzle | Schema source of truth, type-safe queries |
| Auth | BetterAuth | Self-hosted, PostgreSQL adapter |
| UI Components | shadcn/ui | Lyra style, Stone theme, no border radius |
| Icons | Remix Icons | `@remixicon/react` |
| Font | JetBrains Mono | Monospace for financial data |
| Charts | Recharts + shadcn/ui charts | Midday-inspired implementations |
| Tables | shadcn/ui tables | Built on TanStack Table |
| State (Server) | TanStack Query | Data fetching, caching, synchronization |
| State (UI) | Zustand | Sidebar state, filters, preferences |
| Forms | React Hook Form + Zod | Validation, type inference |
| Styling | Tailwind CSS 4 | CSS variables for theming |

### 3.2 Backend Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Framework | FastAPI | Async, OpenAPI docs |
| Language | Python 3.11+ | Type hints throughout |
| ORM | SQLAlchemy 2.0 | Reads/writes to shared schema |
| Migrations | Drizzle (frontend) | Schema managed by Drizzle, SQLAlchemy mirrors it |
| Job Queue | Celery + Redis | Scheduled tasks, background jobs |

### 3.3 Infrastructure

| Service | Version | Purpose |
|---------|---------|---------|
| PostgreSQL | 16 | Primary database (shared) |
| Redis | 7 | Job queues, caching, session store |
| Docker Compose | 3.8+ | Local dev + deployment |

---

## 4. Database Schema

### 4.1 Schema Ownership

- **Drizzle** owns the schema and migrations
- **SQLAlchemy** models mirror the Drizzle schema (manually synced)
- Both connect to the same PostgreSQL instance

### 4.2 Core Tables

#### Authentication (BetterAuth)

```sql
-- Users table (BetterAuth managed)
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    name TEXT,
    email TEXT UNIQUE NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    image TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Sessions table (BetterAuth managed)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Auth accounts (OAuth providers)
CREATE TABLE auth_accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    access_token TEXT,
    refresh_token TEXT,
    access_token_expires_at TIMESTAMP,
    refresh_token_expires_at TIMESTAMP,
    scope TEXT,
    id_token TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Verification tokens (email verification, password reset)
CREATE TABLE verification_tokens (
    id TEXT PRIMARY KEY,
    identifier TEXT NOT NULL,
    token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

#### Application Tables

```sql
-- Bank accounts
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    account_type VARCHAR(50) NOT NULL, -- checking, savings, credit
    institution VARCHAR(255),
    currency CHAR(3) DEFAULT 'EUR',
    provider VARCHAR(50), -- gocardless, manual
    external_id VARCHAR(255), -- Provider's account ID
    balance_current DECIMAL(15,2) DEFAULT 0,
    balance_available DECIMAL(15,2),
    is_active BOOLEAN DEFAULT TRUE,
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, provider, external_id)
);

-- Transaction categories
CREATE TABLE categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    parent_id UUID REFERENCES categories(id),
    category_type VARCHAR(20) DEFAULT 'expense', -- expense, income, transfer
    color VARCHAR(7), -- Hex color
    icon VARCHAR(50), -- Remix icon name
    is_system BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, name, parent_id)
);

-- Transactions
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
    external_id VARCHAR(255),
    transaction_type VARCHAR(20), -- debit, credit
    amount DECIMAL(15,2) NOT NULL,
    currency CHAR(3) DEFAULT 'EUR',
    description TEXT,
    merchant VARCHAR(255),
    category_id UUID REFERENCES categories(id),
    booked_at TIMESTAMP NOT NULL,
    pending BOOLEAN DEFAULT FALSE,
    notes TEXT,
    enrichment_data JSONB, -- Enriched merchant info, logos, etc.
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(account_id, external_id)
);

-- Categorization rules
CREATE TABLE categorization_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    category_id UUID REFERENCES categories(id) ON DELETE CASCADE,
    rule_type VARCHAR(20), -- keyword, regex, merchant, amount_range
    pattern TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);


-- Indexes
CREATE INDEX idx_transactions_user ON transactions(user_id);
CREATE INDEX idx_transactions_account ON transactions(account_id);
CREATE INDEX idx_transactions_booked_at ON transactions(booked_at DESC);
CREATE INDEX idx_transactions_category ON transactions(category_id);
CREATE INDEX idx_accounts_user ON accounts(user_id);
CREATE INDEX idx_categories_user ON categories(user_id);
```

---

## 5. Frontend Architecture

### 5.1 Folder Structure

```
frontend/
├── app/
│   ├── (auth)/                     # Auth route group (no sidebar)
│   │   ├── login/
│   │   │   └── page.tsx
│   │   ├── register/
│   │   │   └── page.tsx
│   │   └── layout.tsx              # Centered auth layout
│   │
│   ├── (dashboard)/                # Main app route group (with sidebar)
│   │   ├── layout.tsx              # Sidebar + header layout
│   │   ├── page.tsx                # Home/Dashboard
│   │   ├── transactions/
│   │   │   ├── page.tsx            # Transaction list
│   │   │   └── [id]/
│   │   │       └── page.tsx        # Transaction detail
│   │   └── settings/
│   │       ├── page.tsx            # General settings
│   │       ├── accounts/
│   │       │   └── page.tsx        # Bank account management
│   │       └── categories/
│   │           └── page.tsx        # Category management
│   │
│   ├── api/
│   │   └── auth/
│   │       └── [...all]/
│   │           └── route.ts        # BetterAuth API handler
│   │
│   ├── layout.tsx                  # Root layout (providers)
│   ├── globals.css                 # Tailwind + CSS variables
│   └── favicon.ico
│
├── components/
│   ├── ui/                         # shadcn/ui components
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── table.tsx
│   │   ├── chart.tsx               # Recharts wrapper
│   │   └── ...
│   │
│   ├── layout/
│   │   ├── sidebar.tsx             # Expandable sidebar
│   │   ├── sidebar-nav.tsx         # Navigation items
│   │   ├── header.tsx              # Top header
│   │   └── user-menu.tsx           # User dropdown
│   │
│   ├── charts/
│   │   ├── cash-balance-chart.tsx  # KPI balance display
│   │   ├── transaction-summary.tsx # Daily transaction chart
│   │   ├── spending-by-category.tsx
│   │   └── cashflow-chart.tsx      # Income vs expenses
│   │
│   ├── transactions/
│   │   ├── transaction-table.tsx   # Data table
│   │   ├── transaction-filters.tsx # Filter controls
│   │   ├── transaction-row.tsx     # Table row
│   │   └── category-badge.tsx      # Category pill
│   │
│   └── accounts/
│       └── account-card.tsx        # Account balance card
│
├── lib/
│   ├── db/
│   │   ├── index.ts                # Drizzle client
│   │   ├── schema.ts               # Drizzle schema definitions
│   │   └── migrations/             # Drizzle migrations
│   │
│   ├── auth.ts                     # BetterAuth configuration
│   ├── auth-client.ts              # BetterAuth client
│   │
│   ├── actions/
│   │   ├── accounts.ts             # Account CRUD actions
│   │   ├── transactions.ts         # Transaction CRUD actions
│   │   ├── categories.ts           # Category CRUD actions
│   │   └── analytics.ts            # Analytics query actions
│   │
│   ├── queries/
│   │   ├── use-accounts.ts         # TanStack Query hooks
│   │   ├── use-transactions.ts
│   │   └── use-analytics.ts
│   │
│   ├── stores/
│   │   └── ui-store.ts             # Zustand store (sidebar, filters)
│   │
│   └── utils.ts                    # Utility functions
│
├── types/
│   ├── index.ts                    # Shared types
│   └── database.ts                 # Drizzle inferred types
│
├── drizzle.config.ts               # Drizzle configuration
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

### 5.2 Key Pages

#### Home/Dashboard (`/`)

- **KPI Card**: Current total cash balance across all accounts
- **Transaction Summary Chart**: Bar/area chart showing daily transactions (last 30 days)
- **Recent Transactions**: Latest 5-10 transactions
- **Quick Actions**: Add transaction, sync accounts

#### Transactions (`/transactions`)

- **Data Table**: Sortable, filterable transaction list using shadcn/ui table
- **Filters**: Date range, account, category, search
- **Bulk Actions**: Categorize multiple transactions
- **Inline Editing**: Quick category assignment

#### Settings (`/settings`)

- **General**: User preferences, currency
- **Accounts**: Connected bank accounts, manual accounts
- **Categories**: Category tree, create/edit categories

### 5.3 Component Patterns

#### Server Components (Default)

```tsx
// app/(dashboard)/page.tsx
import { db } from "@/lib/db";
import { accounts, transactions } from "@/lib/db/schema";
import { CashBalanceCard } from "@/components/charts/cash-balance-chart";

export default async function DashboardPage() {
  const totalBalance = await db
    .select({ total: sum(accounts.balanceCurrent) })
    .from(accounts)
    .where(eq(accounts.isActive, true));

  return (
    <div className="grid gap-4">
      <CashBalanceCard balance={totalBalance[0].total} />
      {/* More components */}
    </div>
  );
}
```

#### Server Actions

```tsx
// lib/actions/transactions.ts
"use server";

import { db } from "@/lib/db";
import { transactions } from "@/lib/db/schema";
import { auth } from "@/lib/auth";
import { revalidatePath } from "next/cache";

export async function updateTransactionCategory(
  transactionId: string,
  categoryId: string
) {
  const session = await auth();
  if (!session) throw new Error("Unauthorized");

  await db
    .update(transactions)
    .set({ categoryId, updatedAt: new Date() })
    .where(eq(transactions.id, transactionId));

  revalidatePath("/transactions");
}
```

---

## 6. Backend Architecture

### 6.1 Responsibilities

The Python backend is a **data pipeline service** that handles:

1. **Cron Jobs**: Scheduled data processing tasks
2. **Enrichment**: Merchant name normalization, logo fetching
3. **Categorization**: Rule-based and AI categorization
4. **Reconciliation**: Deduplication, balance verification
5. **Data Processing**: Processing and analyzing transaction data

### 6.2 Folder Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app (minimal API)
│   ├── database.py                 # SQLAlchemy setup
│   ├── models.py                   # SQLAlchemy models (mirror Drizzle)
│   │
│   ├── integrations/
│   │   ├── __init__.py
│   │   └── base.py                 # Base integration interfaces
│   │
│   └── services/
│       ├── __init__.py
│       ├── sync_service.py         # Orchestrates sync pipeline
│       ├── enrichment_service.py   # Merchant enrichment
│       ├── category_matcher.py     # Auto-categorization
│       └── reconciliation.py       # Deduplication logic
│
├── worker/
│   ├── celery_app.py               # Celery configuration
│   └── tasks/
│       ├── __init__.py
│       ├── bank_sync.py            # Sync tasks
│       └── scheduled.py            # Cron job definitions
│
├── alembic/
│   ├── env.py
│   └── versions/
│
├── requirements.txt
└── Dockerfile
```

### 6.3 Data Pipeline Flow

```mermaid
sequenceDiagram
    participant Cron as Celery Beat
    participant Worker as Celery Worker
    participant Enrich as Enrichment
    participant Cat as Categorizer
    participant DB as PostgreSQL

    Cron->>Worker: Trigger data processing task
    Worker->>DB: Get transactions to process
    Worker->>Enrich: Normalize & enrich
    Enrich-->>Worker: Enriched transactions
    Worker->>Cat: Apply categorization rules
    Cat-->>Worker: Categorized transactions
    Worker->>DB: Update transactions
    Worker->>DB: Update analytics
```

---

## 7. Authentication Flow

### 7.1 BetterAuth Setup

```typescript
// lib/auth.ts
import { betterAuth } from "better-auth";
import { drizzleAdapter } from "better-auth/adapters/drizzle";
import { db } from "@/lib/db";

export const auth = betterAuth({
  database: drizzleAdapter(db, {
    provider: "pg",
  }),
  emailAndPassword: {
    enabled: true,
  },
  session: {
    expiresIn: 60 * 60 * 24 * 7, // 7 days
    updateAge: 60 * 60 * 24, // 1 day
  },
});
```

### 7.2 Auth Flow Diagram

```mermaid
sequenceDiagram
    participant Browser
    participant NextJS as Next.js
    participant Auth as BetterAuth
    participant DB as PostgreSQL

    Browser->>NextJS: POST /api/auth/sign-in
    NextJS->>Auth: Validate credentials
    Auth->>DB: Check user exists
    DB-->>Auth: User record
    Auth->>DB: Create session
    Auth-->>NextJS: Session token
    NextJS-->>Browser: Set cookie + redirect

    Browser->>NextJS: GET /dashboard
    NextJS->>Auth: Validate session cookie
    Auth->>DB: Check session
    DB-->>Auth: Valid session
    Auth-->>NextJS: User context
    NextJS-->>Browser: Render page
```

### 7.3 Protecting Routes

```typescript
// app/(dashboard)/layout.tsx
import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();

  if (!session) {
    redirect("/login");
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1">{children}</main>
    </div>
  );
}
```

---

## 8. Docker Configuration

### 8.1 docker-compose.yml (Root)

```yaml
version: "3.8"

services:
  postgres:
    image: postgres:16-alpine
    container_name: finance-db
    environment:
      POSTGRES_USER: finance
      POSTGRES_PASSWORD: finance_secret
      POSTGRES_DB: finance
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U finance"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: finance-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: finance-frontend
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: postgres://finance:finance_secret@postgres:5432/finance
      BETTER_AUTH_SECRET: your-secret-key-here
      BETTER_AUTH_URL: http://localhost:3000
    depends_on:
      postgres:
        condition: service_healthy

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: finance-backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgres://finance:finance_secret@postgres:5432/finance
      REDIS_URL: redis://redis:6379/0
      OPENAI_API_KEY: your-openai-key
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  celery-worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: finance-worker
    command: celery -A worker.celery_app worker --loglevel=info
    environment:
      DATABASE_URL: postgres://finance:finance_secret@postgres:5432/finance
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - backend
      - redis

  celery-beat:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: finance-beat
    command: celery -A worker.celery_app beat --loglevel=info
    environment:
      DATABASE_URL: postgres://finance:finance_secret@postgres:5432/finance
      REDIS_URL: redis://redis:6379/0
    depends_on:
      - backend
      - redis

volumes:
  postgres_data:
  redis_data:
```

### 8.2 Environment Variables

| Variable | Service | Description |
|----------|---------|-------------|
| `DATABASE_URL` | All | PostgreSQL connection string |
| `REDIS_URL` | Backend | Redis connection string |
| `BETTER_AUTH_SECRET` | Frontend | Session encryption key |
| `BETTER_AUTH_URL` | Frontend | App URL for callbacks |
| `OPENAI_API_KEY` | Backend | OpenAI API for categorization |

---

## 9. Development Workflow

### 9.1 Initial Setup

```bash
# 1. Start infrastructure
docker-compose up -d postgres redis

# 2. Setup frontend
cd frontend
pnpm install
cp .env.example .env.local
pnpm db:push          # Push Drizzle schema to DB
pnpm dev              # Start dev server

# 3. Setup backend (separate terminal)
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head  # Run migrations
uvicorn app.main:app --reload
```

### 9.2 Database Migrations

**Frontend (Drizzle) - Source of Truth:**

```bash
cd frontend
pnpm db:generate      # Generate migration from schema changes
pnpm db:push          # Push to database (dev)
pnpm db:migrate       # Run migrations (production)
```

**Backend (Alembic) - Keep in Sync:**

```bash
cd backend
# After Drizzle migration, update SQLAlchemy models manually
alembic revision --autogenerate -m "sync with drizzle"
alembic upgrade head
```

### 9.3 Running Tests

```bash
# Frontend
cd frontend
pnpm test             # Vitest
pnpm test:e2e         # Playwright

# Backend
cd backend
pytest
```

---

## 10. Data Flow

### 10.1 User Views Transactions

```mermaid
sequenceDiagram
    participant Browser
    participant RSC as React Server Component
    participant Drizzle
    participant DB as PostgreSQL

    Browser->>RSC: GET /transactions
    RSC->>Drizzle: Query transactions
    Drizzle->>DB: SELECT with filters
    DB-->>Drizzle: Transaction rows
    Drizzle-->>RSC: Typed results
    RSC-->>Browser: Rendered HTML
```

### 10.2 Backend Syncs Transactions

```mermaid
sequenceDiagram
    participant Beat as Celery Beat
    participant Worker as Celery Worker
    participant SQLAlchemy
    participant DB as PostgreSQL

    Beat->>Worker: process_transactions (scheduled)
    Worker->>DB: Get transactions to process
    loop For each transaction
        Worker->>Worker: Enrich & categorize
        Worker->>SQLAlchemy: Update transaction
        SQLAlchemy->>DB: UPDATE transaction
    end
    Worker->>DB: Update processing timestamp
```

### 10.3 User Categorizes Transaction

```mermaid
sequenceDiagram
    participant Browser
    participant SA as Server Action
    participant Drizzle
    participant DB as PostgreSQL

    Browser->>SA: updateCategory(txId, catId)
    SA->>SA: Verify session
    SA->>Drizzle: UPDATE transaction
    Drizzle->>DB: UPDATE SET category_id
    DB-->>Drizzle: Success
    SA->>SA: revalidatePath("/transactions")
    SA-->>Browser: Success response
    Browser->>Browser: UI updates automatically
```

---

## 11. Sidebar Navigation Structure

```
┌─────────────────────────────────┐
│  [Logo]  Finance App      [<>]  │  <- Collapse toggle
├─────────────────────────────────┤
│                                 │
│  ◉ Home                         │  <- /
│  ◎ Transactions                 │  <- /transactions
│  ◎ Settings                     │  <- /settings
│                                 │
├─────────────────────────────────┤
│                                 │
│  [User Avatar]                  │
│  user@email.com                 │
│  ▼ Dropdown                     │
│                                 │
└─────────────────────────────────┘
```

### Navigation Items

| Icon | Label | Path | Description |
|------|-------|------|-------------|
| `RiHomeLine` | Home | `/` | Dashboard with KPIs and charts |
| `RiExchangeLine` | Transactions | `/transactions` | Transaction list and management |
| `RiSettings3Line` | Settings | `/settings` | App settings, accounts, categories |

---

## 12. Chart Specifications

### 12.1 Cash Balance KPI Card

- **Type**: Stat card with optional sparkline
- **Data**: Sum of all account balances
- **Update**: Real-time on page load
- **Inspiration**: Midday's balance display

### 12.2 Transaction Summary Chart

- **Type**: Bar chart (daily aggregation)
- **Data**: Daily income (positive) vs expenses (negative)
- **Period**: Last 30 days default
- **Interaction**: Hover for details, click to filter
- **Library**: Recharts BarChart

### 12.3 Spending by Category

- **Type**: Donut/pie chart
- **Data**: Expense totals grouped by category
- **Period**: Current month
- **Interaction**: Click slice to view transactions

---

## 13. Future Considerations

### Phase 2 Features

- Investment portfolio tracking
- Budget management
- Recurring transaction detection
- Multi-currency support
- Export to CSV/PDF

### Technical Improvements

- Real-time updates via WebSockets
- Offline support with service workers
- Mobile app (React Native or PWA)
- ML-based categorization
