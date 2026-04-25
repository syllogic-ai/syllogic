# Investments — Design Spec

**Date:** 2026-04-19
**Status:** Draft for review
**Scope:** v1 of the Investments instrument in Syllogic. Ships IBKR (Interactive Brokers) sync via Flex Web Service and a manual-holdings flow with a daily price-fetch job. Both paths share data model, sync orchestration, and UI.

## Goals

1. Let an IBKR user link their account and have positions, cash, and trades synced into Syllogic daily, contributing to net worth automatically.
2. Let any user (no broker required) enter holdings manually and have a daily job fetch close prices to compute portfolio value over time.
3. Surface investments in the existing dashboard alongside bank accounts, properties, and vehicles, with a dedicated Investments page for portfolio-specific views.

## Non-goals (v1)

- Real-time / intraday price updates.
- Order placement, transfers, or any write operations to brokerages.
- Bonds, options, futures, mutual funds — equities + ETFs + cash only.
- Multi-broker support beyond IBKR Flex (the model is forward-compatible; new providers slot in later).
- Tax-lot accounting beyond a simple `avg_cost` per holding.

## Decisions (from brainstorming)

| Decision | Choice | Reason |
|---|---|---|
| Scope | Both IBKR + manual, shipped together | One coherent feature |
| IBKR access method | Flex Web Service | No gateway, no daily relogin, daily-snapshot fits the cadence |
| Manual price source | Pluggable provider, Yahoo default | Zero-config out of the box, swappable |
| Instrument coverage | Equities, ETFs, multi-currency cash | Covers retail portfolios + IBKR cash positions |
| Historical valuation | Manual: from `as_of_date`. IBKR: reconstructed from trade history | Best fidelity per source without extra API cost |
| UI placement | Investment accounts in Accounts list **and** dedicated Investments page **and** portfolio card on home page | Net-worth rollup + rich drilldown |
| Credential storage | Fernet-encrypted at rest using `SYLLOGIC_SECRET_KEY` | Self-hosters get hygiene; reusable for future broker tokens |
| Sync cadence | Single global Celery-beat at 02:00 UTC, fans out per-user tasks | Simple, predictable |

## Data model

### Extensions to existing tables

**`Account`** — extend the type column with two new values:
- `investment_brokerage` — IBKR-synced (or future broker-synced).
- `investment_manual` — user-entered holdings.

The account's `balance` field stores total portfolio value in the user's base currency. This makes investments roll into net-worth and monthly cashflow automatically through the existing `AccountBalance` machinery. No changes to `BankConnection`.

### New tables

**`broker_connection`** — one row per linked brokerage.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → user | |
| `account_id` | uuid FK → account | The investment_brokerage Account this populates |
| `provider` | enum | `ibkr_flex` (v1). Future: `ibkr_oauth`, `schwab`, etc. |
| `credentials_encrypted` | bytea | Fernet-encrypted JSON `{flex_token, query_id_positions, query_id_trades}` |
| `last_sync_at` | timestamptz | |
| `last_sync_status` | enum | `ok`, `pending`, `error`, `needs_reauth` |
| `last_sync_error` | text | |
| `created_at`, `updated_at` | timestamptz | |

**`holding`** — one position in one instrument inside one account.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK | |
| `account_id` | uuid FK → account | |
| `symbol` | text | Canonical (`AAPL`, `VWCE.DE`). For cash holdings: ISO currency code (`USD`). |
| `name` | text | Resolved at create time; refreshed on sync |
| `currency` | text | Instrument currency (3-letter ISO) |
| `instrument_type` | enum | `equity`, `etf`, `cash` |
| `quantity` | numeric(28,8) | |
| `avg_cost` | numeric(28,8) NULL | Per-unit; reconstructed by IBKR sync, optional manual entry |
| `as_of_date` | date | Manual users: "since when". IBKR: earliest trade date. |
| `source` | enum | `manual`, `ibkr_flex` |
| `last_price_error` | text NULL | Set when most recent price fetch failed |
| `created_at`, `updated_at` | timestamptz | |

Unique on `(account_id, symbol, instrument_type)`. `cash` holdings skip price lookups and use `quantity` as the value in `currency`.

**`broker_trade`** — historical trade (IBKR only; manual flow uses `as_of_date`).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `account_id` | uuid FK | |
| `symbol` | text | |
| `trade_date` | date | |
| `side` | enum | `buy`, `sell` |
| `quantity` | numeric(28,8) | |
| `price` | numeric(28,8) | |
| `currency` | text | |
| `external_id` | text | IBKR trade id; unique on `(account_id, external_id)` |

**`price_snapshot`** — daily close per symbol, shared across users.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `symbol` | text | |
| `currency` | text | |
| `date` | date | |
| `close` | numeric(28,8) | |
| `provider` | enum | `yahoo`, `alpha_vantage`, `manual`, `ibkr` |

Unique on `(symbol, date)`. Cached aggressively — fetched once per day per symbol regardless of holder count.

**`holding_valuation`** — daily computed value per holding.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `holding_id` | uuid FK → holding | |
| `date` | date | |
| `quantity` | numeric(28,8) | snapshot |
| `price` | numeric(28,8) | snapshot in instrument currency |
| `value_user_currency` | numeric(28,8) | After FX |
| `is_stale` | bool | true if price came from older PriceSnapshot |

Unique on `(holding_id, date)`. Denormalized for fast chart queries; storage cost is small (one row per holding per day).

The existing `account_balance` table is reused — the daily job writes one row per investment account with `balance = sum(holding_valuation.value_user_currency)`. The existing `exchange_rate` table + `exchange_rate_service` handles FX conversion; no new FX work.

## Module layout

```
backend/app/integrations/
  ibkr_flex_adapter.py            # request/poll/download Flex statement, parse XML
  price_provider/
    base.py                       # PriceProvider protocol
    yahoo_provider.py             # default impl (yfinance or direct query)
    alpha_vantage_provider.py     # stub for v1
    __init__.py                   # factory reads SYLLOGIC_PRICE_PROVIDER

backend/app/services/
  investment_sync_service.py      # orchestrates one account's sync
  price_service.py                # cache-first lookup, batch fetch
  holding_valuation_service.py    # writes holding_valuation + account_balance
  credentials_crypto.py           # Fernet wrapper using SYLLOGIC_SECRET_KEY

backend/app/routes/
  investments.py                  # REST endpoints

backend/tasks/
  investment_tasks.py             # Celery tasks (per-account + fan-out)

backend/celery_app.py             # add beat schedule entry @ 02:00 UTC

frontend/app/(dashboard)/investments/
  page.tsx                        # portfolio overview
  [holdingId]/page.tsx            # per-holding detail
  connect/page.tsx                # add broker connection or manual account

frontend/components/investments/
  PortfolioSummaryCard.tsx        # appended to bottom of home dashboard
  HoldingsTable.tsx
  AllocationChart.tsx

frontend/lib/api/investments.ts   # typed API client
```

The `PriceProvider` protocol:

```python
class PriceProvider(Protocol):
    def get_daily_close(self, symbol: str, date: date) -> PriceQuote | None: ...
    def get_daily_closes(self, symbols: list[str], date: date) -> dict[str, PriceQuote]: ...
    def search_symbols(self, query: str) -> list[SymbolMatch]: ...
```

## API surface

All endpoints under `/api/investments`, scoped by authenticated `user_id`.

### Broker connections

- `POST /broker-connections` — body: `{provider, flex_token, query_id_positions, query_id_trades, account_name, base_currency}`. Creates `Account` + `BrokerConnection` (encrypted creds). Triggers initial sync. Returns `{connection_id, account_id, sync_task_id}`.
- `GET /broker-connections` — list connections with `last_sync_at`, `last_sync_status`, `last_sync_error`.
- `POST /broker-connections/{id}/sync` — manual re-sync trigger.
- `DELETE /broker-connections/{id}` — disconnect; keeps historical data, marks account inactive.

### Manual brokerage accounts & holdings

- `POST /manual-accounts` — body: `{name, base_currency}`. Creates `Account` (type `investment_manual`).
- `POST /manual-accounts/{account_id}/holdings` — body: `{symbol, quantity, instrument_type, currency, as_of_date, avg_cost?}`. Validates symbol against price provider before saving (422 if unknown).
- `PATCH /holdings/{holding_id}` — manual holdings only.
- `DELETE /holdings/{holding_id}` — manual only; IBKR holdings are read-only and reset on next sync.

### Read endpoints

- `GET /portfolio` — `{total_value, total_value_today_change, currency, accounts, allocation_by_type, allocation_by_currency}`.
- `GET /holdings?account_id=...` — list with current price + value.
- `GET /holdings/{id}/history?from=&to=` — daily valuation series.
- `GET /portfolio/history?from=&to=` — total portfolio value series (sums `account_balance` for investment accounts).
- `GET /symbols/search?q=...` — symbol lookup proxied to provider.

### Errors

- Symbol-validation failures on holding creation: 422.
- Flex token problems: 400 on create, surfaced in connection list afterwards.
- Per-symbol price-fetch failures during sync: do not fail the sync; the holding is rendered with the most recent `price_snapshot` and `is_stale=true`.

## MCP server tools

Added to existing `backend/mcp_server.py` (same auth pattern as the rest). All read-only in v1.

- `list_holdings(account_id?: str)` — returns holdings with current price, value in instrument currency, value in user currency, day change.
- `get_portfolio_summary()` — total value, day change, allocation by instrument type and by currency.
- `get_holding(holding_id: str)` — full detail including avg cost, P&L, and last sync time.
- `get_holding_history(holding_id: str, from: date, to: date)` — daily valuation series for charts/analysis.
- `get_portfolio_history(from: date, to: date)` — total portfolio value over time.
- `list_broker_connections()` — connections with last sync status (helpful for "is my data fresh?" queries).
- `search_symbols(query: str)` — wraps the provider symbol search; useful when a user asks the model to add a holding (the model can confirm the canonical symbol before suggesting the user creates it via the UI).

## Daily sync flow

**Beat task** `daily_investment_sync_all` runs at `02:00 UTC`:

1. Enumerate active investment accounts (both `investment_brokerage` with non-disabled `BrokerConnection` and `investment_manual`).
2. For each, enqueue `sync_investment_account(account_id)`.
3. Worker tasks have `rate_limit` set on the price-provider side (start at 5/sec, tunable).

**Per-account task** `sync_investment_account(account_id)`:

```
if account.type == investment_brokerage:
    statement = ibkr_flex_adapter.fetch_latest(connection)
    upsert holdings from statement.positions
    upsert trades   from statement.trades  → broker_trade
    on first-sync: backfill price_snapshot from earliest trade_date to today

# converged path
symbols = distinct(holding.symbol where instrument_type != 'cash')
prices  = price_service.get_or_fetch(symbols, today)
holding_valuation_service.compute(account, today)   # writes holding_valuation + account_balance
event_publisher.broadcast("account.balance.updated", ...)
```

### Idempotency

Re-running for the same date upserts (unique constraints on `(holding_id, date)` and `(symbol, date)`). Safe to retry.

### Failure modes

| Failure | Handling |
|---|---|
| Flex statement not yet ready | Adapter returns `RETRY`; task reschedules with exponential backoff (max 6 retries over ~3h) |
| Flex token expired/revoked | Write `last_sync_error`, set `last_sync_status=needs_reauth`, surface UI banner. No further retries until user re-enters token. |
| Price provider rate-limited | Per-symbol fetch logs + skips; valuation falls back to last known snapshot with `is_stale=true` |
| Symbol not found | Manual flow validates upfront; if a delisted symbol is encountered later, mark `last_price_error` and surface in UI |
| Worker crash mid-sync | Per-account transaction wraps holding/valuation upserts; partial state rolled back; next beat retries |

### Observability

- Structured logs via the existing logger.
- `BrokerConnection.last_sync_at / last_sync_status / last_sync_error` is the per-user signal.
- Metrics (logged, Prometheus-compatible if scraped): `investment_sync_duration`, `investment_sync_failures_total{reason}`, `price_fetch_duration{provider}`.

### On-demand syncs

`POST /broker-connections/{id}/sync` and the user adding/editing a manual holding both enqueue the same `sync_investment_account` task. UI shows a "Syncing…" state via the existing event channel.

## Security

- Flex tokens are credentials. Stored as Fernet-encrypted bytes in `broker_connection.credentials_encrypted`. Key from `SYLLOGIC_SECRET_KEY` env var (existing convention; if missing, app refuses to start when the investments module is loaded with broker connections present).
- The encryption helper (`credentials_crypto.py`) is generic and is the only path that touches plaintext credentials. All other code reads/writes through it.
- API keys for external price providers (Alpha Vantage, etc.) live in env vars, never in the DB. Yahoo default needs no key.
- All API endpoints scope queries by authenticated `user_id`. Same multi-tenant pattern as the rest of the codebase.

## Configuration (env vars)

| Var | Default | Purpose |
|---|---|---|
| `SYLLOGIC_SECRET_KEY` | (required if any BrokerConnection exists) | Fernet key for credential encryption |
| `SYLLOGIC_PRICE_PROVIDER` | `yahoo` | Active price provider |
| `SYLLOGIC_PRICE_PROVIDER_API_KEY` | (provider-specific, optional) | E.g. Alpha Vantage key |
| `SYLLOGIC_INVESTMENT_SYNC_HOUR_UTC` | `2` | Beat schedule hour |

## Migrations

Single Alembic migration adding the new tables and the two new `account.type` enum values. Backfill: none — feature is opt-in per user. Existing accounts unaffected.

## Testing

- Unit tests for `ibkr_flex_adapter` against recorded XML fixtures (sample positions + trades).
- Unit tests for `yahoo_provider` against recorded HTTP responses.
- Integration test for `sync_investment_account` covering: first sync (with backfill), incremental sync, Flex-not-ready retry, expired-token path, price-fetch partial failure.
- API tests for each route, including auth scoping.
- Frontend component tests for `PortfolioSummaryCard`, `HoldingsTable`, allocation chart.

## Open questions to revisit later (out of v1 scope)

- IBKR OAuth integration for hosted multi-tenant deployments (avoids users generating Flex tokens manually).
- Tax-lot accounting and realized-gain reporting.
- Dividend tracking as a transaction type (Flex statements include this; we can route dividends into the existing `transaction` table later).
- Bonds, options, futures.
