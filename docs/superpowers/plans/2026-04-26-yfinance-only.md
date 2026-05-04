# yfinance-Only Price Provider — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `YahooPriceProvider` (yfinance) the sole price/symbol-search provider; delete `AlphaVantagePriceProvider` and its env vars entirely.

**Architecture:** Single provider behind the existing `PriceProvider` Protocol. `get_price_provider()` returns `YahooPriceProvider()` unconditionally — no env-var branching, no AV code, no API key. The Protocol stays so a future swap is possible, but no switching logic exists.

**Tech Stack:** Python 3.9, FastAPI, Celery, SQLAlchemy, pytest, yfinance ≥ 0.2.0

**Reference spec:** `docs/superpowers/specs/2026-04-26-yfinance-only-design.md`

---

## File Map

| File | Action |
| --- | --- |
| `backend/app/integrations/price_provider/__init__.py` | Modify — drop env-var branching |
| `backend/app/integrations/price_provider/alpha_vantage_provider.py` | **Delete** |
| `backend/tests/test_alpha_vantage_price_provider.py` | **Delete** |
| `backend/tests/test_price_provider_factory.py` | **Create** — pin the new factory behaviour |
| `backend/.env` | Remove `SYLLOGIC_PRICE_PROVIDER`, `SYLLOGIC_PRICE_PROVIDER_API_KEY` (lines 72–73) |
| `backend/.env.example` | Remove same vars + their comment block (lines 57–60) |

**No changes needed for this migration in:** `ExchangeRateService` (already on yfinance), Celery beat schedule, frontend. Adjacent work on this branch (`provider_symbol`, ON CONFLICT, BackgroundTasks, edit-symbol) touches the other modules but is independent of the provider switch.

---

## Task 1: Factory test pinning yfinance-only behaviour (TDD)

**Files:**
- Create: `backend/tests/test_price_provider_factory.py`
- Modify: `backend/app/integrations/price_provider/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_price_provider_factory.py` with this exact content:

```python
"""Pin the factory to yfinance-only behaviour."""
import os
from unittest.mock import patch

from app.integrations.price_provider import get_price_provider
from app.integrations.price_provider.yahoo_provider import YahooPriceProvider


def test_factory_returns_yahoo_provider_with_no_env_vars():
    with patch.dict(os.environ, {}, clear=False):
        for var in ("SYLLOGIC_PRICE_PROVIDER", "SYLLOGIC_PRICE_PROVIDER_API_KEY"):
            os.environ.pop(var, None)
        provider = get_price_provider()
    assert isinstance(provider, YahooPriceProvider)
    assert provider.name == "yahoo"


def test_factory_ignores_legacy_env_vars():
    """Even if old env vars linger from a stale deployment, they have no effect."""
    with patch.dict(
        os.environ,
        {
            "SYLLOGIC_PRICE_PROVIDER": "alpha_vantage",
            "SYLLOGIC_PRICE_PROVIDER_API_KEY": "irrelevant",
        },
    ):
        provider = get_price_provider()
    assert isinstance(provider, YahooPriceProvider)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_price_provider_factory.py -v
```

Expected: `test_factory_ignores_legacy_env_vars` FAILS — current factory tries to instantiate `AlphaVantagePriceProvider` when the env var is set. (`test_factory_returns_yahoo_provider_with_no_env_vars` may pass by accident if the AV branch defaults; that's fine — the second test pins the new behaviour.)

- [ ] **Step 3: Replace the factory**

Replace the entire contents of `backend/app/integrations/price_provider/__init__.py` with:

```python
from .base import PriceProvider, PriceQuote, SymbolMatch
from .yahoo_provider import YahooPriceProvider

__all__ = ["PriceProvider", "PriceQuote", "SymbolMatch", "get_price_provider"]


def get_price_provider() -> PriceProvider:
    """Return the active price provider. yfinance-backed, no configuration."""
    return YahooPriceProvider()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_price_provider_factory.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/integrations/price_provider/__init__.py \
        backend/tests/test_price_provider_factory.py
git commit -m "refactor(price-provider): factory always returns YahooPriceProvider

Drop SYLLOGIC_PRICE_PROVIDER env-var branching. yfinance is the sole
provider; the AV branch is removed and the env var is ignored."
```

---

## Task 2: Delete Alpha Vantage provider and tests

**Files:**
- Delete: `backend/app/integrations/price_provider/alpha_vantage_provider.py`
- Delete: `backend/tests/test_alpha_vantage_price_provider.py`

- [ ] **Step 1: Delete the provider source file**

```bash
rm backend/app/integrations/price_provider/alpha_vantage_provider.py
```

- [ ] **Step 2: Delete the AV test file**

```bash
rm backend/tests/test_alpha_vantage_price_provider.py
```

- [ ] **Step 3: Verify no other code imports the deleted module**

```bash
cd backend && python -c "from app.integrations.price_provider import get_price_provider; p = get_price_provider(); print(p.name)"
```

Expected output: `yahoo`

Also grep for stragglers:

```bash
cd backend && grep -rn "alpha_vantage\|AlphaVantage" app tests 2>/dev/null | grep -v __pycache__
```

Expected output: empty (no matches).

- [ ] **Step 4: Run the price-provider factory + Yahoo tests**

```bash
cd backend && python -m pytest tests/test_price_provider_factory.py tests/test_yahoo_price_provider.py -v
```

Expected: all pass (3 yahoo tests + 2 factory tests = 5 passed).

- [ ] **Step 5: Commit**

```bash
git add -A backend/app/integrations/price_provider/alpha_vantage_provider.py \
              backend/tests/test_alpha_vantage_price_provider.py
git commit -m "chore(price-provider): delete AlphaVantagePriceProvider and tests"
```

---

## Task 3: Clean env files

**Files:**
- Modify: `backend/.env` (lines 72–73)
- Modify: `backend/.env.example` (lines 57–60)

- [ ] **Step 1: Remove the env vars from `backend/.env`**

Remove these two lines (currently at lines 72–73) from `backend/.env`:

```
SYLLOGIC_PRICE_PROVIDER=alpha_vantage
SYLLOGIC_PRICE_PROVIDER_API_KEY=<REDACTED>
```

Use the Edit tool with `old_string`:
```
SYLLOGIC_PRICE_PROVIDER=alpha_vantage
SYLLOGIC_PRICE_PROVIDER_API_KEY=<REDACTED>
```
and `new_string`: empty string.

- [ ] **Step 2: Remove the env vars from `backend/.env.example`**

Remove lines 57–60 from `backend/.env.example`:

```
# Investments price provider. Options: alpha_vantage (default), yahoo
SYLLOGIC_PRICE_PROVIDER=alpha_vantage
# Required when SYLLOGIC_PRICE_PROVIDER=alpha_vantage. Free key works for dev (25 req/day).
SYLLOGIC_PRICE_PROVIDER_API_KEY=
```

Use the Edit tool with `old_string`:
```
# Investments price provider. Options: alpha_vantage (default), yahoo
SYLLOGIC_PRICE_PROVIDER=alpha_vantage
# Required when SYLLOGIC_PRICE_PROVIDER=alpha_vantage. Free key works for dev (25 req/day).
SYLLOGIC_PRICE_PROVIDER_API_KEY=
```
and `new_string`: empty string.

- [ ] **Step 3: Verify env vars are gone**

```bash
grep -n "SYLLOGIC_PRICE_PROVIDER" backend/.env backend/.env.example 2>/dev/null
```

Expected: empty (no matches).

- [ ] **Step 4: Verify backend still boots locally**

The local backend reads `.env` via python-dotenv on import. Restart the running uvicorn:

```bash
pkill -f "uvicorn app.main:app" 2>/dev/null; sleep 2
cd backend && PYTHONPATH=. uvicorn app.main:app --port 8000 &
sleep 4
curl -s http://localhost:8000/health
```

Expected output: `{"status":"healthy"}`

- [ ] **Step 5: Commit**

```bash
git add backend/.env backend/.env.example
git commit -m "chore(env): drop SYLLOGIC_PRICE_PROVIDER and API key

yfinance is the only provider now; no configuration needed."
```

---

## Task 4: Full test suite + manual smoke test

**Files:** none modified.

- [ ] **Step 1: Run the full backend test suite**

```bash
cd backend && python -m pytest -v 2>&1 | tail -40
```

Expected: all tests pass. The line count of pass/fail should match the prior baseline minus the 7 deleted AV tests (`test_alpha_vantage_price_provider.py` had 7 test functions) plus the 2 new factory tests.

- [ ] **Step 2: Manual smoke — symbol search via Yahoo**

```bash
cd backend && PYTHONPATH=. python -c "
from app.integrations.price_provider import get_price_provider
p = get_price_provider()
print('Provider:', p.name)
print('Search VUAA:')
for m in p.search_symbols('VUAA')[:5]:
    print(f'  {m.symbol:12} {m.name[:40]:40} {m.exchange}')
"
```

Expected output: provider `yahoo`, and at least one match for `VUAA` (e.g. `VUAA.L`, `VUAA.AS`, `VUAA.MI`).

- [ ] **Step 3: Manual smoke — bulk price fetch**

```bash
cd backend && PYTHONPATH=. python -c "
from datetime import date
from app.integrations.price_provider import get_price_provider
p = get_price_provider()
quotes = p.get_daily_closes(['AAPL', 'MSFT', 'VUAA.L'], date.today())
for sym, q in quotes.items():
    print(f'{sym:10} {q.close} {q.currency} ({q.date})')
"
```

Expected output: prices for at least `AAPL` and `MSFT` (USD), and `VUAA.L` (GBp/GBP). All in a single bulk call.

- [ ] **Step 4: Trigger one investments re-sync via the API**

Open the running app at `http://localhost:3000/investments`, click "Refresh prices", and verify in the logs that the Celery worker picks up `sync_investment_account` for each manual investment account, and that VUAA's `current_price` updates from `0` to a real value.

Verify in the DB:

```bash
source backend/.env && psql "$DATABASE_URL" -c "
SELECT h.symbol, h.provider_symbol, hv.price, hv.value_user_currency, hv.is_stale, hv.date
FROM holdings h
JOIN holding_valuations hv ON hv.holding_id = h.id
WHERE hv.date = (SELECT MAX(date) FROM holding_valuations WHERE holding_id = h.id);
"
```

Expected: VUAA row shows a non-zero `price` and `is_stale = false`.

- [ ] **Step 5: Document Railway env cleanup (no commit)**

Print this message to the user:

> Local migration complete. Two manual actions remain on Railway production:
>
> 1. **Remove env vars** from the backend service: `SYLLOGIC_PRICE_PROVIDER` and `SYLLOGIC_PRICE_PROVIDER_API_KEY` (Project → backend service → Variables → delete both).
> 2. After deploy, click **Refresh prices** on `/investments` to repopulate prices via yfinance.

No git commit for this step — it's an operational note.

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- "Architecture: single provider, drop env-var switching" → Task 1
- "Files Changed: AV provider deleted, AV test deleted" → Task 2
- "Files Changed: env files cleaned" → Task 3
- "Testing: keep yahoo tests, delete AV tests, run full suite" → Tasks 2 + 4
- "Migration Ops: remove Railway env vars, refresh prices" → Task 4 step 5

**2. Placeholder scan** — no TBD/TODO/"appropriate"/"similar to" patterns. Every code/command block is concrete.

**3. Type consistency** — `YahooPriceProvider`, `get_price_provider`, `provider.name` ("yahoo"), and `PriceProvider` Protocol are referenced consistently across all tasks.
