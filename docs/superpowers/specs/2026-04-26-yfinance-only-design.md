# yfinance-Only Price Provider — Design

**Status:** Approved
**Date:** 2026-04-26

## Goal

Make yfinance the sole price/symbol-search provider for the investments
subsystem. Delete Alpha Vantage entirely and remove its environment
variables.

## Motivation

Alpha Vantage's free tier (25 req/day, 1 symbol per request) does not
scale beyond a handful of holdings. It also requires per-symbol exchange
suffixes that the free tier sometimes refuses (e.g. `VUAA.LON`).

yfinance, while unofficial, supports:
- Bulk daily closes via `yf.download(tickers=[…])` in one HTTP call
- US, LSE, Euronext, Xetra symbols natively (`AAPL`, `VUAA.L`, `IWDA.AS`)
- Symbol search via `yfinance.Search`
- Effectively unlimited request volume for a once-daily cron job

The risk is occasional breakage when Yahoo changes their internal
endpoints; yfinance typically adapts within days. Acceptable for a
personal-use app.

## Architecture

Single provider behind the existing `PriceProvider` Protocol. The
factory `get_price_provider()` returns `YahooPriceProvider()`
unconditionally. The Protocol stays so the abstraction survives a future
provider swap, but no env-var switching exists.

```
get_price_provider() ──► YahooPriceProvider
                          │
                          ├─ get_daily_close(symbol, on)
                          ├─ get_daily_closes(symbols, on)   ← bulk
                          └─ search_symbols(query)
```

No caller knows the difference; `PriceService`, `HoldingValuationService`,
and the investments API all consume the Protocol.

## Files Changed

| File | Action |
| --- | --- |
| `backend/app/integrations/price_provider/__init__.py` | Simplify factory: drop env-var branching, return `YahooPriceProvider()` |
| `backend/app/integrations/price_provider/alpha_vantage_provider.py` | **Delete** |
| `backend/tests/test_alpha_vantage_price_provider.py` | **Delete** |
| `backend/.env` | Remove `SYLLOGIC_PRICE_PROVIDER`, `SYLLOGIC_PRICE_PROVIDER_API_KEY` |
| `backend/.env.example` | Remove same vars |

**No changes needed for the provider migration itself in:** `ExchangeRateService`
(already uses yfinance), Celery beat schedule, frontend.

(Adjacent work on this branch — `provider_symbol`, ON CONFLICT upsert,
BackgroundTasks, edit-symbol — touches `PriceService`, `HoldingValuationService`,
REST routes, schemas, and frontend, but is independent of this migration's goal
of making yfinance the sole provider.)

## Data Flow (unchanged)

1. Celery beat fires `daily_investment_sync_all` at 02:00 UTC
2. For each manual investment account → `HoldingValuationService.revalue_all`
3. Per holding → `PriceService.latest_snapshot(symbol_or_provider_symbol, on)`
4. On miss → `PriceService.get_or_fetch` calls `provider.get_daily_closes(symbols, on)`
5. Bulk `yf.download(tickers="AAPL VUAA.L IWDA.AS …")` returns one DataFrame
6. Snapshots upserted via `ON CONFLICT DO NOTHING`

## Error Handling

Already in place; no new code:
- `PriceService.get_or_fetch` wraps the provider call in try/except, logs warnings
- Missing snapshots set `is_stale=True` on `HoldingValuation`; UI handles this
- `YahooPriceProvider._currency_for` falls back to `USD` on yfinance errors
- `YahooPriceProvider.search_symbols` falls back to `[SymbolMatch(query.upper(), …)]` on errors

## Testing

- Keep `backend/tests/test_yahoo_price_provider.py` (3 mocked tests)
- Delete `backend/tests/test_alpha_vantage_price_provider.py`
- Run full backend test suite to confirm no other code mocks AV symbols

## Migration Ops (post-deploy)

1. Delete `SYLLOGIC_PRICE_PROVIDER` and `SYLLOGIC_PRICE_PROVIDER_API_KEY`
   from Railway production env vars (manual user action)
2. Restart backend + Celery worker on Railway (auto on env change)
3. Click "Refresh prices" on `/investments` once — queues a sync for
   every active investment account (manual + brokerage), repopulating
   prices via yfinance

## Out of Scope

- Frontend changes — none needed; the symbol-search UX already works
  with whatever provider returns
- FX rate provider — already yfinance-based via `ExchangeRateService`
- Alembic-style migration — there are no schema changes
- Adding a yfinance-specific rate-limit/backoff layer — the once-daily
  cron volume is well under any practical threshold
