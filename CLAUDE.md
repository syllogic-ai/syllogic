# Syllogic - Agent Instructions

## Project Overview

A personal finance app with **two-service architecture**:

- **Frontend (Next.js)**: UI, authentication, CRUD operations via Server Actions + Drizzle ORM
- **Backend (Python)**: Data pipeline for transaction enrichment, categorization, cron jobs

Both services share a single **PostgreSQL** database. Drizzle schema is the source of truth.

---

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
│  - Transaction enrichment & categorization                  │
│  - Celery + Redis (cron jobs)                               │
└─────────────────────────────────────────────────────────────┘
```

---

## MCP Servers - ALWAYS USE THESE

### Context7 MCP Server
Use for **any library documentation, API references, or external service docs**:
- Drizzle ORM docs
- BetterAuth docs
- TanStack Query/Table docs
- Recharts docs
- Any npm package documentation

**When to use**: Before implementing any feature that involves a library you're unsure about.

### shadcn MCP Server
Use for **all shadcn/ui related work**:
- Adding new components (`shadcn add <component>`)
- Finding component examples and usage patterns
- Discovering available blocks and templates
- Checking component APIs and variants

**When to use**: Before creating any UI component, check if shadcn has it first.

### Midday Docs
Use as **inspiration for UI/chart implementations**:
- Financial dashboard layouts
- Transaction tables and filters
- Chart implementations (built on Recharts)
- KPI cards and balance displays
- Date range pickers for financial data

**When to use**: When building charts, dashboards, or financial UI components.

---

## Tech Stack

### Frontend (`/frontend`)

| Category | Library | Notes |
|----------|---------|-------|
| Framework | Next.js 16+ | App Router, RSC, Server Actions |
| Language | TypeScript | Strict mode |
| ORM | Drizzle | Schema source of truth |
| Auth | BetterAuth | PostgreSQL adapter |
| UI | shadcn/ui | Lyra style, Stone theme, no radius |
| Icons | Remix Icons | `@remixicon/react` |
| Font | JetBrains Mono | Monospace |
| Charts | Recharts | Via shadcn/ui chart components |
| Tables | shadcn/ui tables | Built on TanStack Table |
| State | TanStack Query | Server state |
| Forms | React Hook Form + Zod | Validation |

### Backend (`/backend`)

| Category | Library | Notes |
|----------|---------|-------|
| Framework | FastAPI | Data pipeline only |
| ORM | SQLAlchemy 2.0 | Mirrors Drizzle schema |
| Jobs | Celery + Redis | Scheduled tasks |

### Infrastructure

| Service | Purpose |
|---------|---------|
| PostgreSQL 16 | Shared database |
| Redis 7 | Job queues, caching |
| Docker Compose | All services |

---

## Key Patterns

### Data Operations (Frontend)
```typescript
// ALWAYS use Server Actions for mutations
"use server";
import { db } from "@/lib/db";
import { transactions } from "@/lib/db/schema";

export async function updateCategory(txId: string, categoryId: string) {
  await db.update(transactions)
    .set({ categoryId })
    .where(eq(transactions.id, txId));
  revalidatePath("/transactions");
}
```

### Authentication
```typescript
// Protect routes with BetterAuth
import { auth } from "@/lib/auth";
import { redirect } from "next/navigation";

export default async function ProtectedPage() {
  const session = await auth();
  if (!session) redirect("/login");
  // ...
}
```

### Charts (Use Midday as Reference)
```typescript
// Use shadcn/ui chart components built on Recharts
import { BarChart, Bar, XAxis, YAxis } from "recharts";
// Check Midday for financial chart patterns
```

---

## Folder Structure

```
/
├── frontend/
│   ├── app/
│   │   ├── (auth)/           # Login, register (no sidebar)
│   │   ├── (dashboard)/      # Main app (with sidebar)
│   │   │   ├── page.tsx      # Home/Dashboard
│   │   │   ├── transactions/
│   │   │   └── settings/
│   │   └── api/auth/[...all]/ # BetterAuth handler
│   ├── components/
│   │   ├── ui/               # shadcn components
│   │   ├── layout/           # Sidebar, Header
│   │   └── charts/           # Recharts wrappers
│   ├── lib/
│   │   ├── db/               # Drizzle client + schema
│   │   ├── auth.ts           # BetterAuth config
│   │   └── actions/          # Server Actions
│   └── drizzle.config.ts
├── backend/
│   └── (existing Python structure)
├── docs/
│   └── architecture.md       # Detailed architecture
└── docker-compose.yml
```

---

## UI Guidelines

### shadcn/ui Configuration
- **Style**: Lyra (base-lyra)
- **Base Color**: Stone
- **Theme**: Stone
- **Radius**: None (0)
- **Font**: JetBrains Mono
- **Icons**: Remix Icons
- **Menu Color**: Default
- **Menu Accent**: Subtle

### Component Priority
1. **Check shadcn MCP** for existing components first
2. **Check Midday** for financial UI patterns
3. Build custom only if necessary

### Sidebar Navigation
| Icon | Label | Path |
|------|-------|------|
| `RiHomeLine` | Home | `/` |
| `RiExchangeLine` | Transactions | `/transactions` |
| `RiSettings3Line` | Settings | `/settings` |

---

## Commands

### Frontend
```bash
cd frontend
pnpm dev              # Start dev server
pnpm db:push          # Push schema to DB
pnpm db:generate      # Generate migration
pnpm db:studio        # Open Drizzle Studio
```

### Backend
```bash
cd backend
uvicorn app.main:app --reload  # Start API
celery -A worker.celery_app worker  # Start worker
```

### Docker
```bash
docker-compose up -d postgres redis  # Start infra
docker-compose up                    # Start all
```

---

## Before You Code

1. **Check MCP servers** for documentation
2. **Read `docs/architecture.md`** for detailed specs
3. **Use Server Actions** for all data mutations
4. **Use shadcn components** before building custom
5. **Reference Midday** for financial UI patterns

---

## Environment Variables

```env
# Frontend (.env.local)
DATABASE_URL=postgres://finance:finance_secret@localhost:5432/finance
BETTER_AUTH_SECRET=your-secret-key
BETTER_AUTH_URL=http://localhost:3000

# Backend (.env)
DATABASE_URL=postgres://finance:finance_secret@localhost:5432/finance
REDIS_URL=redis://localhost:6379/0
```
