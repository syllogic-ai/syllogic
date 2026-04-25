# Investments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the v1 Investments feature: IBKR Flex sync + manual holdings + daily price-fetch + UI surfaces, per [docs/superpowers/specs/2026-04-19-investments-design.md](../specs/2026-04-19-investments-design.md).

**Architecture:** Schema is added to Drizzle first (`frontend/lib/db/schema.ts`) and a hand-written SQL migration in `frontend/lib/db/migrations/`, then mirrored in SQLAlchemy (`backend/app/models.py`). Backend gets a pluggable `PriceProvider` (Yahoo default), an `IBKRFlexAdapter`, three services (`price_service`, `holding_valuation_service`, `investment_sync_service`), Celery tasks fanned out from a daily 02:00 UTC beat, REST endpoints under `/api/investments`, and read-only MCP tools. Frontend gets an Investments page, per-holding detail, connect wizard, and a `PortfolioSummaryCard` on the dashboard home.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / Celery / Redis · Drizzle (PG) · Next.js App Router / React / TS · `yfinance` (existing dependency) · `cryptography` (Fernet) · `httpx` (existing) · `pytest`.

**Conventions enforced:**
- TDD per task: write failing test → run → implement → run → commit.
- Schema lives in Drizzle; SQLAlchemy mirrors. Migration is a hand-written numbered SQL file (next number after `0004_remove_bank_connections.sql`).
- All API endpoints scope by `get_user_id(user_id)` from `app/db_helpers.py`.
- Money/quantity columns use `Numeric(28, 8)`; FX-converted values use `Numeric(15, 2)` to match existing `account.balance_available`.
- Commit after every passing test step.

---

## File Structure

### New files

**Backend**
- `backend/app/integrations/ibkr_flex_adapter.py`
- `backend/app/integrations/price_provider/__init__.py`
- `backend/app/integrations/price_provider/base.py`
- `backend/app/integrations/price_provider/yahoo_provider.py`
- `backend/app/integrations/price_provider/alpha_vantage_provider.py`
- `backend/app/services/credentials_crypto.py`
- `backend/app/services/price_service.py`
- `backend/app/services/holding_valuation_service.py`
- `backend/app/services/investment_sync_service.py`
- `backend/app/routes/investments.py`
- `backend/app/mcp/tools/investments.py`
- `backend/tasks/investment_tasks.py`
- `backend/tests/test_credentials_crypto.py`
- `backend/tests/test_yahoo_price_provider.py`
- `backend/tests/test_ibkr_flex_adapter.py`
- `backend/tests/test_price_service.py`
- `backend/tests/test_holding_valuation_service.py`
- `backend/tests/test_investment_sync_service.py`
- `backend/tests/test_investment_tasks.py`
- `backend/tests/test_investments_routes.py`
- `backend/tests/test_mcp_investments_tools.py`
- `backend/tests/fixtures/ibkr_flex_positions.xml`
- `backend/tests/fixtures/ibkr_flex_trades.xml`

**Frontend**
- `frontend/lib/db/migrations/0005_investments.sql`
- `frontend/lib/api/investments.ts`
- `frontend/app/(dashboard)/investments/page.tsx`
- `frontend/app/(dashboard)/investments/[holdingId]/page.tsx`
- `frontend/app/(dashboard)/investments/connect/page.tsx`
- `frontend/components/investments/PortfolioSummaryCard.tsx`
- `frontend/components/investments/HoldingsTable.tsx`
- `frontend/components/investments/AllocationChart.tsx`
- `frontend/components/investments/ConnectIBKRForm.tsx`
- `frontend/components/investments/AddManualHoldingForm.tsx`

### Modified files

- `frontend/lib/db/schema.ts` — add `brokerConnections`, `holdings`, `brokerTrades`, `priceSnapshots`, `holdingValuations`; extend `accounts.accountType` allowed values.
- `backend/app/models.py` — add SQLAlchemy classes for the new tables.
- `backend/app/schemas.py` — add Pydantic schemas for investments endpoints.
- `backend/app/routes/__init__.py` — register `investments` router.
- `backend/app/mcp/server.py` (or `app/mcp/tools/__init__.py`) — register the new tools module.
- `backend/celery_app.py` — add `daily-investment-sync-all` to beat schedule and add `tasks.investment_tasks` to `include`.
- `backend/requirements.txt` — add `cryptography` if not already present.
- `frontend/app/(dashboard)/page.tsx` (home dashboard) — append `<PortfolioSummaryCard />` at the bottom.
- Account-detail page — render `<HoldingsTable />` when account type is investment.

---

## Phase 1 — Schema & encryption infra

### Task 1: Drizzle schema additions

**Files:**
- Modify: `frontend/lib/db/schema.ts`

- [ ] **Step 1: Add new tables to `schema.ts`**

Append these table definitions (use existing imports for `pgTable`, `uuid`, `text`, `timestamp`, `numeric`, `boolean`, `date`, `pgEnum`, `index`, `uniqueIndex`):

```ts
export const brokerConnections = pgTable("broker_connections", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  accountId: uuid("account_id").notNull().references(() => accounts.id, { onDelete: "cascade" }),
  provider: text("provider").notNull(), // 'ibkr_flex'
  credentialsEncrypted: text("credentials_encrypted").notNull(), // base64 fernet
  lastSyncAt: timestamp("last_sync_at"),
  lastSyncStatus: text("last_sync_status").default("pending"), // ok|pending|error|needs_reauth
  lastSyncError: text("last_sync_error"),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
});

export const holdings = pgTable("holdings", {
  id: uuid("id").primaryKey().defaultRandom(),
  userId: text("user_id").notNull().references(() => users.id, { onDelete: "cascade" }),
  accountId: uuid("account_id").notNull().references(() => accounts.id, { onDelete: "cascade" }),
  symbol: text("symbol").notNull(),
  name: text("name"),
  currency: text("currency").notNull(),
  instrumentType: text("instrument_type").notNull(), // equity|etf|cash
  quantity: numeric("quantity", { precision: 28, scale: 8 }).notNull(),
  avgCost: numeric("avg_cost", { precision: 28, scale: 8 }),
  asOfDate: date("as_of_date"),
  source: text("source").notNull(), // manual|ibkr_flex
  lastPriceError: text("last_price_error"),
  createdAt: timestamp("created_at").defaultNow(),
  updatedAt: timestamp("updated_at").defaultNow(),
}, (t) => ({
  uniqHolding: uniqueIndex("holdings_account_symbol_type_uq").on(t.accountId, t.symbol, t.instrumentType),
  byAccount: index("idx_holdings_account").on(t.accountId),
}));

export const brokerTrades = pgTable("broker_trades", {
  id: uuid("id").primaryKey().defaultRandom(),
  accountId: uuid("account_id").notNull().references(() => accounts.id, { onDelete: "cascade" }),
  symbol: text("symbol").notNull(),
  tradeDate: date("trade_date").notNull(),
  side: text("side").notNull(), // buy|sell
  quantity: numeric("quantity", { precision: 28, scale: 8 }).notNull(),
  price: numeric("price", { precision: 28, scale: 8 }).notNull(),
  currency: text("currency").notNull(),
  externalId: text("external_id").notNull(),
}, (t) => ({
  uniqTrade: uniqueIndex("broker_trades_account_external_uq").on(t.accountId, t.externalId),
}));

export const priceSnapshots = pgTable("price_snapshots", {
  id: uuid("id").primaryKey().defaultRandom(),
  symbol: text("symbol").notNull(),
  currency: text("currency").notNull(),
  date: date("date").notNull(),
  close: numeric("close", { precision: 28, scale: 8 }).notNull(),
  provider: text("provider").notNull(), // yahoo|alpha_vantage|manual|ibkr
}, (t) => ({
  uniqSnap: uniqueIndex("price_snapshots_symbol_date_uq").on(t.symbol, t.date),
}));

export const holdingValuations = pgTable("holding_valuations", {
  id: uuid("id").primaryKey().defaultRandom(),
  holdingId: uuid("holding_id").notNull().references(() => holdings.id, { onDelete: "cascade" }),
  date: date("date").notNull(),
  quantity: numeric("quantity", { precision: 28, scale: 8 }).notNull(),
  price: numeric("price", { precision: 28, scale: 8 }).notNull(),
  valueUserCurrency: numeric("value_user_currency", { precision: 15, scale: 2 }).notNull(),
  isStale: boolean("is_stale").default(false),
}, (t) => ({
  uniqVal: uniqueIndex("holding_valuations_holding_date_uq").on(t.holdingId, t.date),
}));
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS (no new TS errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/db/schema.ts
git commit -m "feat(investments): add drizzle schema for holdings/connections/prices"
```

---

### Task 2: SQL migration `0005_investments.sql`

**Files:**
- Create: `frontend/lib/db/migrations/0005_investments.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Broker connections
CREATE TABLE IF NOT EXISTS broker_connections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  provider text NOT NULL,
  credentials_encrypted text NOT NULL,
  last_sync_at timestamp,
  last_sync_status text DEFAULT 'pending',
  last_sync_error text,
  created_at timestamp DEFAULT now(),
  updated_at timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_broker_connections_user ON broker_connections(user_id);

-- Holdings
CREATE TABLE IF NOT EXISTS holdings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  symbol text NOT NULL,
  name text,
  currency text NOT NULL,
  instrument_type text NOT NULL,
  quantity numeric(28,8) NOT NULL,
  avg_cost numeric(28,8),
  as_of_date date,
  source text NOT NULL,
  last_price_error text,
  created_at timestamp DEFAULT now(),
  updated_at timestamp DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS holdings_account_symbol_type_uq ON holdings(account_id, symbol, instrument_type);
CREATE INDEX IF NOT EXISTS idx_holdings_account ON holdings(account_id);

-- Broker trades
CREATE TABLE IF NOT EXISTS broker_trades (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  symbol text NOT NULL,
  trade_date date NOT NULL,
  side text NOT NULL,
  quantity numeric(28,8) NOT NULL,
  price numeric(28,8) NOT NULL,
  currency text NOT NULL,
  external_id text NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS broker_trades_account_external_uq ON broker_trades(account_id, external_id);

-- Price snapshots
CREATE TABLE IF NOT EXISTS price_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  currency text NOT NULL,
  date date NOT NULL,
  close numeric(28,8) NOT NULL,
  provider text NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS price_snapshots_symbol_date_uq ON price_snapshots(symbol, date);

-- Holding valuations
CREATE TABLE IF NOT EXISTS holding_valuations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  holding_id uuid NOT NULL REFERENCES holdings(id) ON DELETE CASCADE,
  date date NOT NULL,
  quantity numeric(28,8) NOT NULL,
  price numeric(28,8) NOT NULL,
  value_user_currency numeric(15,2) NOT NULL,
  is_stale boolean DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS holding_valuations_holding_date_uq ON holding_valuations(holding_id, date);
```

- [ ] **Step 2: Apply migration locally**

Run: `cd frontend && pnpm drizzle-kit migrate` (or whatever the existing project script is — check `package.json` "scripts" if unclear).
Expected: migration applied, no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/db/migrations/0005_investments.sql
git commit -m "feat(investments): add 0005 migration for investment tables"
```

---

### Task 3: SQLAlchemy mirrors

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1: Append the five new model classes at the end of `models.py`**

```python
class BrokerConnection(Base):
    __tablename__ = "broker_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(50), nullable=False)
    credentials_encrypted = Column(Text, nullable=False)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(20), default="pending")
    last_sync_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account")


class Holding(Base):
    __tablename__ = "holdings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(64), nullable=False)
    name = Column(String(255))
    currency = Column(String(3), nullable=False)
    instrument_type = Column(String(20), nullable=False)
    quantity = Column(Numeric(28, 8), nullable=False)
    avg_cost = Column(Numeric(28, 8), nullable=True)
    as_of_date = Column(DateTime, nullable=True)
    source = Column(String(20), nullable=False)
    last_price_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    valuations = relationship("HoldingValuation", back_populates="holding", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("account_id", "symbol", "instrument_type", name="holdings_account_symbol_type_uq"),
        Index("idx_holdings_account", "account_id"),
    )


class BrokerTrade(Base):
    __tablename__ = "broker_trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False)
    symbol = Column(String(64), nullable=False)
    trade_date = Column(DateTime, nullable=False)
    side = Column(String(10), nullable=False)
    quantity = Column(Numeric(28, 8), nullable=False)
    price = Column(Numeric(28, 8), nullable=False)
    currency = Column(String(3), nullable=False)
    external_id = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("account_id", "external_id", name="broker_trades_account_external_uq"),
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(64), nullable=False)
    currency = Column(String(3), nullable=False)
    date = Column(DateTime, nullable=False)
    close = Column(Numeric(28, 8), nullable=False)
    provider = Column(String(20), nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="price_snapshots_symbol_date_uq"),
    )


class HoldingValuation(Base):
    __tablename__ = "holding_valuations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    holding_id = Column(UUID(as_uuid=True), ForeignKey("holdings.id", ondelete="CASCADE"), nullable=False)
    date = Column(DateTime, nullable=False)
    quantity = Column(Numeric(28, 8), nullable=False)
    price = Column(Numeric(28, 8), nullable=False)
    value_user_currency = Column(Numeric(15, 2), nullable=False)
    is_stale = Column(Boolean, default=False)

    holding = relationship("Holding", back_populates="valuations")

    __table_args__ = (
        UniqueConstraint("holding_id", "date", name="holding_valuations_holding_date_uq"),
    )
```

- [ ] **Step 2: Verify import**

Run: `cd backend && python -c "from app.models import BrokerConnection, Holding, BrokerTrade, PriceSnapshot, HoldingValuation; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models.py
git commit -m "feat(investments): add sqlalchemy mirrors for investment tables"
```

---

### Task 4: Credential encryption helper

**Files:**
- Create: `backend/app/services/credentials_crypto.py`
- Test: `backend/tests/test_credentials_crypto.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_credentials_crypto.py
import os
import json
import pytest
from app.services import credentials_crypto


def test_round_trip_encrypts_and_decrypts(monkeypatch):
    monkeypatch.setenv("SYLLOGIC_SECRET_KEY", credentials_crypto.generate_key())
    payload = {"flex_token": "abc", "query_id_positions": "111"}
    blob = credentials_crypto.encrypt(payload)
    assert isinstance(blob, str)
    assert "abc" not in blob
    assert credentials_crypto.decrypt(blob) == payload


def test_decrypt_rejects_tampered_blob(monkeypatch):
    monkeypatch.setenv("SYLLOGIC_SECRET_KEY", credentials_crypto.generate_key())
    blob = credentials_crypto.encrypt({"a": "b"})
    tampered = blob[:-2] + ("AA" if blob[-2:] != "AA" else "BB")
    with pytest.raises(credentials_crypto.CredentialDecryptError):
        credentials_crypto.decrypt(tampered)


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("SYLLOGIC_SECRET_KEY", raising=False)
    with pytest.raises(credentials_crypto.CredentialKeyMissing):
        credentials_crypto.encrypt({"x": 1})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_credentials_crypto.py -v`
Expected: ImportError / module not found.

- [ ] **Step 3: Implement**

```python
# backend/app/services/credentials_crypto.py
import json
import os
from cryptography.fernet import Fernet, InvalidToken


class CredentialKeyMissing(RuntimeError):
    pass


class CredentialDecryptError(RuntimeError):
    pass


def generate_key() -> str:
    """Generate a new Fernet key (base64). Use for tests / first-time setup."""
    return Fernet.generate_key().decode()


def _fernet() -> Fernet:
    key = os.getenv("SYLLOGIC_SECRET_KEY")
    if not key:
        raise CredentialKeyMissing("SYLLOGIC_SECRET_KEY env var is required to encrypt/decrypt credentials")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(payload: dict) -> str:
    return _fernet().encrypt(json.dumps(payload, sort_keys=True).encode()).decode()


def decrypt(blob: str) -> dict:
    try:
        raw = _fernet().decrypt(blob.encode())
    except InvalidToken as e:
        raise CredentialDecryptError("Invalid or tampered credential blob") from e
    return json.loads(raw.decode())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_credentials_crypto.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Add `cryptography` to requirements if missing**

Run: `grep -q '^cryptography' backend/requirements.txt || echo 'cryptography>=42.0' >> backend/requirements.txt`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/credentials_crypto.py backend/tests/test_credentials_crypto.py backend/requirements.txt
git commit -m "feat(investments): fernet credential encryption helper"
```

---

## Phase 2 — Price provider

### Task 5: `PriceProvider` protocol

**Files:**
- Create: `backend/app/integrations/price_provider/__init__.py`
- Create: `backend/app/integrations/price_provider/base.py`

- [ ] **Step 1: Write the protocol and types**

```python
# backend/app/integrations/price_provider/base.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class PriceQuote:
    symbol: str
    currency: str
    date: date
    close: Decimal


@dataclass(frozen=True)
class SymbolMatch:
    symbol: str
    name: str
    exchange: str | None
    currency: str | None


class PriceProvider(Protocol):
    name: str

    def get_daily_close(self, symbol: str, on: date) -> PriceQuote | None: ...
    def get_daily_closes(self, symbols: list[str], on: date) -> dict[str, PriceQuote]: ...
    def search_symbols(self, query: str) -> list[SymbolMatch]: ...
```

- [ ] **Step 2: Write the factory**

```python
# backend/app/integrations/price_provider/__init__.py
import os
from .base import PriceProvider, PriceQuote, SymbolMatch
from .yahoo_provider import YahooPriceProvider

__all__ = ["PriceProvider", "PriceQuote", "SymbolMatch", "get_price_provider"]


def get_price_provider() -> PriceProvider:
    name = os.getenv("SYLLOGIC_PRICE_PROVIDER", "yahoo").lower()
    if name == "yahoo":
        return YahooPriceProvider()
    if name == "alpha_vantage":
        from .alpha_vantage_provider import AlphaVantagePriceProvider
        return AlphaVantagePriceProvider(api_key=os.environ["SYLLOGIC_PRICE_PROVIDER_API_KEY"])
    raise ValueError(f"Unknown price provider: {name}")
```

- [ ] **Step 3: Commit (no tests yet — protocol-only)**

```bash
git add backend/app/integrations/price_provider/__init__.py backend/app/integrations/price_provider/base.py
git commit -m "feat(investments): PriceProvider protocol + factory"
```

---

### Task 6: Yahoo price provider

**Files:**
- Create: `backend/app/integrations/price_provider/yahoo_provider.py`
- Create: `backend/app/integrations/price_provider/alpha_vantage_provider.py` (stub)
- Test: `backend/tests/test_yahoo_price_provider.py`

- [ ] **Step 1: Write the failing test (mock yfinance)**

```python
# backend/tests/test_yahoo_price_provider.py
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pandas as pd

from app.integrations.price_provider.yahoo_provider import YahooPriceProvider


def _df(rows):
    return pd.DataFrame(rows).set_index("Date")


def test_get_daily_close_returns_quote():
    fake = _df([{"Date": pd.Timestamp("2026-04-18"), "Close": 234.56}])
    with patch("app.integrations.price_provider.yahoo_provider.yf") as yf_mod:
        ticker = MagicMock()
        ticker.history.return_value = fake
        ticker.info = {"currency": "USD"}
        yf_mod.Ticker.return_value = ticker
        q = YahooPriceProvider().get_daily_close("AAPL", date(2026, 4, 18))
    assert q is not None
    assert q.symbol == "AAPL"
    assert q.currency == "USD"
    assert q.close == Decimal("234.56")
    assert q.date == date(2026, 4, 18)


def test_get_daily_close_returns_none_when_no_data():
    with patch("app.integrations.price_provider.yahoo_provider.yf") as yf_mod:
        ticker = MagicMock()
        ticker.history.return_value = pd.DataFrame()
        yf_mod.Ticker.return_value = ticker
        assert YahooPriceProvider().get_daily_close("ZZZZ", date(2026, 4, 18)) is None


def test_get_daily_closes_batches_symbols():
    rows = [
        {"Date": pd.Timestamp("2026-04-18"), ("Close", "AAPL"): 234.56, ("Close", "MSFT"): 410.10},
    ]
    df = pd.DataFrame(rows).set_index("Date")
    with patch("app.integrations.price_provider.yahoo_provider.yf") as yf_mod:
        yf_mod.download.return_value = df
        # currency lookup falls back to USD if .info missing
        yf_mod.Ticker.return_value = MagicMock(info={"currency": "USD"})
        result = YahooPriceProvider().get_daily_closes(["AAPL", "MSFT"], date(2026, 4, 18))
    assert set(result.keys()) == {"AAPL", "MSFT"}
    assert result["AAPL"].close == Decimal("234.56")
```

- [ ] **Step 2: Run — expect failure**

Run: `cd backend && pytest tests/test_yahoo_price_provider.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement YahooPriceProvider**

```python
# backend/app/integrations/price_provider/yahoo_provider.py
from __future__ import annotations
import logging
from datetime import date, timedelta
from decimal import Decimal
from .base import PriceProvider, PriceQuote, SymbolMatch

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

logger = logging.getLogger(__name__)


class YahooPriceProvider:
    name = "yahoo"

    def _currency_for(self, symbol: str) -> str:
        try:
            info = yf.Ticker(symbol).info or {}
            return (info.get("currency") or "USD").upper()
        except Exception:
            return "USD"

    def get_daily_close(self, symbol: str, on: date) -> PriceQuote | None:
        if yf is None:
            raise RuntimeError("yfinance is not installed")
        # Yahoo returns the row keyed by trading day; pull a small window to handle weekends/holidays.
        start = on - timedelta(days=5)
        end = on + timedelta(days=1)
        df = yf.Ticker(symbol).history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False)
        if df is None or df.empty:
            return None
        # Pick the last row at or before `on`.
        df = df[df.index.date <= on]
        if df.empty:
            return None
        row = df.iloc[-1]
        return PriceQuote(
            symbol=symbol,
            currency=self._currency_for(symbol),
            date=df.index[-1].date(),
            close=Decimal(str(row["Close"])),
        )

    def get_daily_closes(self, symbols: list[str], on: date) -> dict[str, PriceQuote]:
        if not symbols:
            return {}
        if yf is None:
            raise RuntimeError("yfinance is not installed")
        start = on - timedelta(days=5)
        end = on + timedelta(days=1)
        data = yf.download(
            tickers=" ".join(symbols),
            start=start.isoformat(),
            end=end.isoformat(),
            group_by="column",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
        out: dict[str, PriceQuote] = {}
        if data is None or data.empty:
            return out
        # Multi-ticker download has MultiIndex columns: top-level "Close" → per-symbol col
        if "Close" not in data.columns.get_level_values(0):
            return out
        closes = data["Close"]
        for sym in symbols:
            if sym not in closes.columns:
                continue
            series = closes[sym].dropna()
            series = series[series.index.date <= on]
            if series.empty:
                continue
            out[sym] = PriceQuote(
                symbol=sym,
                currency=self._currency_for(sym),
                date=series.index[-1].date(),
                close=Decimal(str(series.iloc[-1])),
            )
        return out

    def search_symbols(self, query: str) -> list[SymbolMatch]:
        # Yahoo doesn't expose an official search; use the unofficial endpoint via yfinance's `Search` if available,
        # otherwise return a minimal echo so the UI still works.
        try:
            from yfinance import Search  # type: ignore
            results = Search(query, max_results=10).quotes or []
            return [
                SymbolMatch(
                    symbol=r.get("symbol", ""),
                    name=r.get("shortname") or r.get("longname") or r.get("symbol", ""),
                    exchange=r.get("exchDisp"),
                    currency=None,
                )
                for r in results
                if r.get("symbol")
            ]
        except Exception:
            return [SymbolMatch(symbol=query.upper(), name=query.upper(), exchange=None, currency=None)]
```

- [ ] **Step 4: Add Alpha Vantage stub (raises NotImplementedError on use)**

```python
# backend/app/integrations/price_provider/alpha_vantage_provider.py
from .base import PriceProvider, PriceQuote, SymbolMatch
from datetime import date


class AlphaVantagePriceProvider:
    name = "alpha_vantage"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_daily_close(self, symbol: str, on: date) -> PriceQuote | None:
        raise NotImplementedError("AlphaVantagePriceProvider not implemented in v1")

    def get_daily_closes(self, symbols, on):  # type: ignore[override]
        raise NotImplementedError

    def search_symbols(self, query: str):
        raise NotImplementedError
```

- [ ] **Step 5: Run — expect pass**

Run: `cd backend && pytest tests/test_yahoo_price_provider.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/price_provider/yahoo_provider.py backend/app/integrations/price_provider/alpha_vantage_provider.py backend/tests/test_yahoo_price_provider.py
git commit -m "feat(investments): yahoo price provider impl + alpha_vantage stub"
```

---

## Phase 3 — IBKR Flex adapter

### Task 7: IBKR Flex adapter — fixtures + parser

**Files:**
- Create: `backend/tests/fixtures/ibkr_flex_positions.xml`
- Create: `backend/tests/fixtures/ibkr_flex_trades.xml`
- Create: `backend/app/integrations/ibkr_flex_adapter.py`
- Test: `backend/tests/test_ibkr_flex_adapter.py`

- [ ] **Step 1: Create fixture XMLs**

`backend/tests/fixtures/ibkr_flex_positions.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse queryName="positions" type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U1234567" fromDate="20260101" toDate="20260418" period="YearToDate">
      <OpenPositions>
        <OpenPosition symbol="AAPL" description="APPLE INC" assetCategory="STK" currency="USD" position="10" markPrice="234.56" costBasisPrice="180.00"/>
        <OpenPosition symbol="VWCE" description="VANGUARD FTSE ALL-WORLD" assetCategory="ETF" currency="EUR" position="42" markPrice="115.20" costBasisPrice="95.10"/>
      </OpenPositions>
      <CashReport>
        <CashReportCurrency currency="USD" endingCash="1500.00"/>
        <CashReportCurrency currency="EUR" endingCash="320.50"/>
      </CashReport>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>
```

`backend/tests/fixtures/ibkr_flex_trades.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<FlexQueryResponse queryName="trades" type="AF">
  <FlexStatements count="1">
    <FlexStatement accountId="U1234567" fromDate="20260101" toDate="20260418" period="YearToDate">
      <Trades>
        <Trade tradeID="T1" symbol="AAPL" assetCategory="STK" currency="USD" tradeDate="20260115" buySell="BUY" quantity="10" tradePrice="180.00"/>
        <Trade tradeID="T2" symbol="VWCE" assetCategory="ETF" currency="EUR" tradeDate="20260201" buySell="BUY" quantity="42" tradePrice="95.10"/>
      </Trades>
    </FlexStatement>
  </FlexStatements>
</FlexQueryResponse>
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_ibkr_flex_adapter.py
from decimal import Decimal
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
import httpx

from app.integrations.ibkr_flex_adapter import (
    IBKRFlexAdapter,
    FlexStatementNotReady,
    FlexAuthError,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_positions_extracts_holdings_and_cash():
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")
    parsed = adapter.parse_positions_xml(_read("ibkr_flex_positions.xml"))
    by_sym = {p.symbol: p for p in parsed.positions}
    assert by_sym["AAPL"].quantity == Decimal("10")
    assert by_sym["AAPL"].currency == "USD"
    assert by_sym["AAPL"].instrument_type == "equity"
    assert by_sym["VWCE"].instrument_type == "etf"
    assert {c.currency: c.balance for c in parsed.cash} == {"USD": Decimal("1500.00"), "EUR": Decimal("320.50")}


def test_parse_trades_extracts_trades():
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")
    trades = adapter.parse_trades_xml(_read("ibkr_flex_trades.xml"))
    assert len(trades) == 2
    t1 = trades[0]
    assert t1.external_id == "T1"
    assert t1.symbol == "AAPL"
    assert t1.side == "buy"
    assert t1.quantity == Decimal("10")
    assert t1.price == Decimal("180.00")
    assert t1.trade_date == date(2026, 1, 15)


def test_request_statement_returns_reference_code(monkeypatch):
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")

    def fake_get(url, params, timeout):
        assert "FlexStatementService.SendRequest" in url
        return httpx.Response(200, text='<FlexStatementResponse><Status>Success</Status><ReferenceCode>REF1</ReferenceCode><Url>https://x</Url></FlexStatementResponse>')

    with patch.object(adapter._client, "get", side_effect=fake_get):
        ref = adapter.request_statement("qp")
    assert ref == "REF1"


def test_fetch_statement_raises_not_ready(monkeypatch):
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")
    response_xml = '<FlexStatementResponse><Status>Warn</Status><ErrorCode>1019</ErrorCode><ErrorMessage>Statement generation in progress</ErrorMessage></FlexStatementResponse>'
    with patch.object(adapter._client, "get", return_value=httpx.Response(200, text=response_xml)):
        with pytest.raises(FlexStatementNotReady):
            adapter.fetch_statement("REF1")


def test_fetch_statement_raises_auth_error():
    adapter = IBKRFlexAdapter(token="t", query_id_positions="qp", query_id_trades="qt")
    response_xml = '<FlexStatementResponse><Status>Fail</Status><ErrorCode>1012</ErrorCode><ErrorMessage>Token invalid</ErrorMessage></FlexStatementResponse>'
    with patch.object(adapter._client, "get", return_value=httpx.Response(200, text=response_xml)):
        with pytest.raises(FlexAuthError):
            adapter.fetch_statement("REF1")
```

- [ ] **Step 3: Run — expect failure**

Run: `cd backend && pytest tests/test_ibkr_flex_adapter.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement adapter**

```python
# backend/app/integrations/ibkr_flex_adapter.py
"""IBKR Flex Web Service adapter.

Two-step flow:
  1. SendRequest with token + query_id → returns reference code
  2. GetStatement with token + reference code → returns XML statement
     (or status=Warn/ErrorCode=1019 if still generating).
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable
import xml.etree.ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

BASE = "https://gdcdyn.interactivebrokers.com/Universal/servlet"
SEND_URL = f"{BASE}/FlexStatementService.SendRequest"
GET_URL = f"{BASE}/FlexStatementService.GetStatement"

FLEX_NOT_READY_CODES = {"1019"}
FLEX_AUTH_ERROR_CODES = {"1012", "1003"}


class FlexError(RuntimeError):
    pass


class FlexStatementNotReady(FlexError):
    pass


class FlexAuthError(FlexError):
    pass


_ASSET_CATEGORY_MAP = {"STK": "equity", "ETF": "etf"}


@dataclass(frozen=True)
class ParsedPosition:
    symbol: str
    name: str
    quantity: Decimal
    currency: str
    instrument_type: str
    avg_cost: Decimal | None
    mark_price: Decimal | None


@dataclass(frozen=True)
class ParsedCash:
    currency: str
    balance: Decimal


@dataclass(frozen=True)
class ParsedStatement:
    positions: list[ParsedPosition]
    cash: list[ParsedCash]


@dataclass(frozen=True)
class ParsedTrade:
    external_id: str
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    currency: str
    trade_date: date


class IBKRFlexAdapter:
    def __init__(self, token: str, query_id_positions: str, query_id_trades: str, *, client: httpx.Client | None = None):
        self.token = token
        self.query_id_positions = query_id_positions
        self.query_id_trades = query_id_trades
        self._client = client or httpx.Client(timeout=30.0)

    # ----- HTTP -----
    def request_statement(self, query_id: str) -> str:
        resp = self._client.get(SEND_URL, params={"v": "3", "t": self.token, "q": query_id}, timeout=30.0)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        status = (root.findtext("Status") or "").strip()
        if status != "Success":
            self._raise_for_error(root)
        return (root.findtext("ReferenceCode") or "").strip()

    def fetch_statement(self, reference_code: str) -> str:
        resp = self._client.get(GET_URL, params={"v": "3", "t": self.token, "q": reference_code}, timeout=60.0)
        resp.raise_for_status()
        # The response is either a FlexQueryResponse (success) or FlexStatementResponse (status pending/error).
        if "<FlexQueryResponse" in resp.text:
            return resp.text
        root = ET.fromstring(resp.text)
        self._raise_for_error(root)
        return resp.text  # unreachable

    def _raise_for_error(self, root: ET.Element) -> None:
        code = (root.findtext("ErrorCode") or "").strip()
        message = (root.findtext("ErrorMessage") or "").strip() or "Unknown Flex error"
        if code in FLEX_NOT_READY_CODES:
            raise FlexStatementNotReady(message)
        if code in FLEX_AUTH_ERROR_CODES:
            raise FlexAuthError(message)
        raise FlexError(f"{code}: {message}")

    # ----- Parsers -----
    def parse_positions_xml(self, xml: str) -> ParsedStatement:
        root = ET.fromstring(xml)
        positions: list[ParsedPosition] = []
        for op in root.iter("OpenPosition"):
            asset = (op.get("assetCategory") or "").upper()
            instrument_type = _ASSET_CATEGORY_MAP.get(asset)
            if instrument_type is None:
                continue  # skip unsupported asset classes in v1
            positions.append(ParsedPosition(
                symbol=op.get("symbol", "").strip(),
                name=op.get("description", "").strip(),
                quantity=Decimal(op.get("position", "0")),
                currency=op.get("currency", "USD").strip().upper(),
                instrument_type=instrument_type,
                avg_cost=_dec(op.get("costBasisPrice")),
                mark_price=_dec(op.get("markPrice")),
            ))
        cash: list[ParsedCash] = []
        for c in root.iter("CashReportCurrency"):
            cur = (c.get("currency") or "").upper()
            if not cur or cur == "BASE_SUMMARY":
                continue
            cash.append(ParsedCash(currency=cur, balance=Decimal(c.get("endingCash", "0"))))
        return ParsedStatement(positions=positions, cash=cash)

    def parse_trades_xml(self, xml: str) -> list[ParsedTrade]:
        root = ET.fromstring(xml)
        trades: list[ParsedTrade] = []
        for t in root.iter("Trade"):
            asset = (t.get("assetCategory") or "").upper()
            if asset not in _ASSET_CATEGORY_MAP:
                continue
            trades.append(ParsedTrade(
                external_id=t.get("tradeID", "").strip(),
                symbol=t.get("symbol", "").strip(),
                side="buy" if t.get("buySell", "BUY").upper() == "BUY" else "sell",
                quantity=Decimal(t.get("quantity", "0")),
                price=Decimal(t.get("tradePrice", "0")),
                currency=t.get("currency", "USD").strip().upper(),
                trade_date=datetime.strptime(t.get("tradeDate", ""), "%Y%m%d").date(),
            ))
        return trades


def _dec(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except Exception:
        return None
```

- [ ] **Step 5: Run — expect pass**

Run: `cd backend && pytest tests/test_ibkr_flex_adapter.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/integrations/ibkr_flex_adapter.py backend/tests/test_ibkr_flex_adapter.py backend/tests/fixtures/
git commit -m "feat(investments): IBKR Flex adapter with positions/trades parsing"
```

---

## Phase 4 — Services

### Task 8: `price_service` — cache-first batch lookup

**Files:**
- Create: `backend/app/services/price_service.py`
- Test: `backend/tests/test_price_service.py`

- [ ] **Step 1: Write the failing test (uses an in-memory sqlite DB)**

```python
# backend/tests/test_price_service.py
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import PriceSnapshot
from app.services.price_service import PriceService
from app.integrations.price_provider.base import PriceQuote


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_returns_cached_snapshot_without_calling_provider(db):
    db.add(PriceSnapshot(symbol="AAPL", currency="USD", date=date(2026, 4, 18),
                         close=Decimal("234.56"), provider="yahoo"))
    db.commit()
    provider = MagicMock()
    svc = PriceService(db=db, provider=provider)
    out = svc.get_or_fetch(["AAPL"], date(2026, 4, 18))
    assert out["AAPL"].close == Decimal("234.56")
    provider.get_daily_closes.assert_not_called()


def test_fetches_missing_and_persists(db):
    provider = MagicMock()
    provider.get_daily_closes.return_value = {
        "MSFT": PriceQuote("MSFT", "USD", date(2026, 4, 18), Decimal("410.10")),
    }
    provider.name = "yahoo"
    svc = PriceService(db=db, provider=provider)
    out = svc.get_or_fetch(["MSFT"], date(2026, 4, 18))
    assert out["MSFT"].close == Decimal("410.10")
    persisted = db.query(PriceSnapshot).filter_by(symbol="MSFT").one()
    assert persisted.close == Decimal("410.10")
    assert persisted.provider == "yahoo"


def test_partial_miss(db):
    db.add(PriceSnapshot(symbol="AAPL", currency="USD", date=date(2026, 4, 18),
                         close=Decimal("234.56"), provider="yahoo"))
    db.commit()
    provider = MagicMock()
    provider.get_daily_closes.return_value = {
        "MSFT": PriceQuote("MSFT", "USD", date(2026, 4, 18), Decimal("410.10")),
    }
    provider.name = "yahoo"
    svc = PriceService(db=db, provider=provider)
    out = svc.get_or_fetch(["AAPL", "MSFT"], date(2026, 4, 18))
    assert set(out.keys()) == {"AAPL", "MSFT"}
    provider.get_daily_closes.assert_called_once_with(["MSFT"], date(2026, 4, 18))
```

- [ ] **Step 2: Run — expect failure**

Run: `cd backend && pytest tests/test_price_service.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# backend/app/services/price_service.py
from __future__ import annotations
from datetime import date
from decimal import Decimal
import logging
from sqlalchemy.orm import Session

from app.models import PriceSnapshot
from app.integrations.price_provider import get_price_provider
from app.integrations.price_provider.base import PriceProvider, PriceQuote

logger = logging.getLogger(__name__)


class PriceService:
    def __init__(self, db: Session, provider: PriceProvider | None = None):
        self.db = db
        self.provider = provider or get_price_provider()

    def get_or_fetch(self, symbols: list[str], on: date) -> dict[str, PriceQuote]:
        if not symbols:
            return {}
        cached_rows = (
            self.db.query(PriceSnapshot)
            .filter(PriceSnapshot.symbol.in_(symbols), PriceSnapshot.date == on)
            .all()
        )
        cached = {
            r.symbol: PriceQuote(symbol=r.symbol, currency=r.currency, date=on, close=Decimal(r.close))
            for r in cached_rows
        }
        missing = [s for s in symbols if s not in cached]
        if missing:
            try:
                fetched = self.provider.get_daily_closes(missing, on)
            except Exception as e:
                logger.warning("price provider %s failed for %s on %s: %s", self.provider.name, missing, on, e)
                fetched = {}
            for sym, quote in fetched.items():
                self.db.add(PriceSnapshot(
                    symbol=quote.symbol,
                    currency=quote.currency,
                    date=quote.date,
                    close=quote.close,
                    provider=self.provider.name,
                ))
                cached[sym] = quote
            self.db.commit()
        return cached

    def latest_snapshot(self, symbol: str, on: date) -> PriceSnapshot | None:
        """Most recent snapshot at or before `on`. Used as a fallback for stale prices."""
        return (
            self.db.query(PriceSnapshot)
            .filter(PriceSnapshot.symbol == symbol, PriceSnapshot.date <= on)
            .order_by(PriceSnapshot.date.desc())
            .first()
        )
```

- [ ] **Step 4: Run — expect pass**

Run: `cd backend && pytest tests/test_price_service.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/price_service.py backend/tests/test_price_service.py
git commit -m "feat(investments): PriceService with cache-first lookup"
```

---

### Task 9: `holding_valuation_service`

**Files:**
- Create: `backend/app/services/holding_valuation_service.py`
- Test: `backend/tests/test_holding_valuation_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_holding_valuation_service.py
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, Holding, PriceSnapshot, HoldingValuation, AccountBalance, User
from app.services.holding_valuation_service import HoldingValuationService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_user(db, currency="EUR"):
    user = User(id="u1", email="u@example.com", base_currency=currency)
    db.add(user)
    db.commit()
    return user


def _make_account(db, user_id, currency="EUR", account_type="investment_manual"):
    a = Account(id=uuid4(), user_id=user_id, name="Brokerage", account_type=account_type, currency=currency)
    db.add(a); db.commit()
    return a


def test_computes_valuation_for_equity_in_user_currency(db):
    user = _make_user(db, currency="EUR")
    acc = _make_account(db, user.id, currency="EUR")
    h = Holding(id=uuid4(), user_id=user.id, account_id=acc.id, symbol="AAPL",
                currency="USD", instrument_type="equity",
                quantity=Decimal("10"), source="manual")
    db.add(h)
    db.add(PriceSnapshot(symbol="AAPL", currency="USD", date=date(2026, 4, 18),
                         close=Decimal("234.56"), provider="yahoo"))
    db.commit()

    fx = MagicMock()
    fx.convert.return_value = Decimal("2199.07")  # 10 * 234.56 USD → EUR
    svc = HoldingValuationService(db=db, fx=fx)
    svc.compute(account_id=acc.id, on=date(2026, 4, 18))

    val = db.query(HoldingValuation).filter_by(holding_id=h.id, date=date(2026, 4, 18)).one()
    assert val.value_user_currency == Decimal("2199.07")
    assert val.is_stale is False

    bal = db.query(AccountBalance).filter_by(account_id=acc.id, date=date(2026, 4, 18)).one()
    assert bal.balance == Decimal("2199.07")


def test_cash_holding_skips_price_lookup(db):
    user = _make_user(db, currency="EUR")
    acc = _make_account(db, user.id, currency="EUR")
    h = Holding(id=uuid4(), user_id=user.id, account_id=acc.id, symbol="USD",
                currency="USD", instrument_type="cash",
                quantity=Decimal("1500"), source="ibkr_flex")
    db.add(h); db.commit()

    fx = MagicMock()
    fx.convert.return_value = Decimal("1380.00")
    svc = HoldingValuationService(db=db, fx=fx)
    svc.compute(account_id=acc.id, on=date(2026, 4, 18))

    val = db.query(HoldingValuation).filter_by(holding_id=h.id).one()
    assert val.price == Decimal("1")
    assert val.value_user_currency == Decimal("1380.00")


def test_marks_stale_when_no_same_day_snapshot(db):
    user = _make_user(db, currency="EUR")
    acc = _make_account(db, user.id, currency="EUR")
    h = Holding(id=uuid4(), user_id=user.id, account_id=acc.id, symbol="AAPL",
                currency="USD", instrument_type="equity",
                quantity=Decimal("10"), source="manual")
    db.add(h)
    db.add(PriceSnapshot(symbol="AAPL", currency="USD", date=date(2026, 4, 17),
                         close=Decimal("230.00"), provider="yahoo"))
    db.commit()
    fx = MagicMock(); fx.convert.return_value = Decimal("2100.00")
    HoldingValuationService(db=db, fx=fx).compute(account_id=acc.id, on=date(2026, 4, 18))
    val = db.query(HoldingValuation).filter_by(holding_id=h.id, date=date(2026, 4, 18)).one()
    assert val.is_stale is True
```

> Note: this test assumes `User.base_currency` exists. If the `User` model doesn't have it, add it as part of this task (`base_currency = Column(String(3), default="EUR")`) and update the migration in Task 2 to add the column to `users`. Verify by reading `backend/app/models.py` — if absent, add it now and reflect it in the Drizzle schema + migration too.

- [ ] **Step 2: Run — expect failure**

Run: `cd backend && pytest tests/test_holding_valuation_service.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement service**

```python
# backend/app/services/holding_valuation_service.py
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Protocol
from uuid import UUID
from sqlalchemy.orm import Session

from app.models import Account, Holding, HoldingValuation, AccountBalance, User
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)


class FxConverter(Protocol):
    def convert(self, amount: Decimal, src: str, dst: str, on: date) -> Decimal: ...


class HoldingValuationService:
    def __init__(self, db: Session, fx: FxConverter, price_service: PriceService | None = None):
        self.db = db
        self.fx = fx
        self.price_service = price_service or PriceService(db=db)

    def compute(self, account_id: UUID, on: date) -> Decimal:
        account = self.db.query(Account).filter_by(id=account_id).one()
        user = self.db.query(User).filter_by(id=account.user_id).one()
        user_currency = (getattr(user, "base_currency", None) or account.currency or "EUR").upper()
        holdings = self.db.query(Holding).filter_by(account_id=account_id).all()

        total = Decimal("0")
        for h in holdings:
            price, currency, is_stale = self._price_for(h, on)
            value_native = (Decimal(h.quantity) * price).quantize(Decimal("0.00000001"))
            value_user = self.fx.convert(value_native, currency, user_currency, on)
            value_user = Decimal(value_user).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self._upsert_valuation(h.id, on, Decimal(h.quantity), price, value_user, is_stale)
            total += value_user

        self._upsert_account_balance(account, on, total)
        self.db.commit()
        return total

    # --- helpers ---
    def _price_for(self, h: Holding, on: date) -> tuple[Decimal, str, bool]:
        if h.instrument_type == "cash":
            return Decimal("1"), h.currency, False
        snap = self.price_service.latest_snapshot(h.symbol, on)
        if snap is None:
            return Decimal("0"), h.currency, True
        return Decimal(snap.close), snap.currency, snap.date != on

    def _upsert_valuation(self, holding_id, on: date, qty: Decimal, price: Decimal,
                          value_user: Decimal, is_stale: bool) -> None:
        row = self.db.query(HoldingValuation).filter_by(holding_id=holding_id, date=on).one_or_none()
        if row is None:
            row = HoldingValuation(holding_id=holding_id, date=on, quantity=qty,
                                   price=price, value_user_currency=value_user, is_stale=is_stale)
            self.db.add(row)
        else:
            row.quantity = qty
            row.price = price
            row.value_user_currency = value_user
            row.is_stale = is_stale

    def _upsert_account_balance(self, account: Account, on: date, total: Decimal) -> None:
        row = self.db.query(AccountBalance).filter_by(account_id=account.id, date=on).one_or_none()
        if row is None:
            row = AccountBalance(account_id=account.id, date=on, balance=total)
            self.db.add(row)
        else:
            row.balance = total
        account.balance_available = total
        account.last_synced_at = __import__("datetime").datetime.utcnow()
```

- [ ] **Step 4: Run — expect pass**

Run: `cd backend && pytest tests/test_holding_valuation_service.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/holding_valuation_service.py backend/tests/test_holding_valuation_service.py
git commit -m "feat(investments): HoldingValuationService with FX + stale-price flag"
```

---

### Task 10: `investment_sync_service`

**Files:**
- Create: `backend/app/services/investment_sync_service.py`
- Test: `backend/tests/test_investment_sync_service.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_investment_sync_service.py
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, BrokerConnection, Holding, BrokerTrade, User
from app.services.investment_sync_service import InvestmentSyncService
from app.services.credentials_crypto import encrypt

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def crypto_key(monkeypatch):
    from app.services import credentials_crypto
    monkeypatch.setenv("SYLLOGIC_SECRET_KEY", credentials_crypto.generate_key())


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_sync_brokerage_upserts_holdings_trades_and_cash(db):
    user = User(id="u1", email="u@example.com", base_currency="EUR")
    acc = Account(id=uuid4(), user_id="u1", name="IBKR", account_type="investment_brokerage", currency="EUR")
    conn = BrokerConnection(id=uuid4(), user_id="u1", account_id=acc.id, provider="ibkr_flex",
                            credentials_encrypted=encrypt({"flex_token": "t",
                                                           "query_id_positions": "qp",
                                                           "query_id_trades": "qt"}))
    db.add_all([user, acc, conn]); db.commit()

    adapter = MagicMock()
    adapter.request_statement.side_effect = ["REF_POS", "REF_TR"]
    adapter.fetch_statement.side_effect = [
        (FIXTURES / "ibkr_flex_positions.xml").read_text(),
        (FIXTURES / "ibkr_flex_trades.xml").read_text(),
    ]
    # Wire parsers through to the real implementation
    from app.integrations.ibkr_flex_adapter import IBKRFlexAdapter as Real
    real = Real(token="t", query_id_positions="qp", query_id_trades="qt")
    adapter.parse_positions_xml.side_effect = real.parse_positions_xml
    adapter.parse_trades_xml.side_effect = real.parse_trades_xml

    fx = MagicMock(); fx.convert.side_effect = lambda amt, src, dst, on: amt  # identity FX

    svc = InvestmentSyncService(db=db, adapter_factory=lambda creds: adapter, fx=fx)
    svc.sync_account(acc.id, on=date(2026, 4, 18))

    holdings = {h.symbol: h for h in db.query(Holding).filter_by(account_id=acc.id).all()}
    assert holdings["AAPL"].quantity == Decimal("10")
    assert holdings["VWCE"].instrument_type == "etf"
    assert holdings["USD"].instrument_type == "cash" and holdings["USD"].quantity == Decimal("1500.00")
    assert holdings["EUR"].quantity == Decimal("320.50")
    trades = db.query(BrokerTrade).filter_by(account_id=acc.id).all()
    assert {t.external_id for t in trades} == {"T1", "T2"}

    db.refresh(conn)
    assert conn.last_sync_status == "ok"
    assert conn.last_sync_at is not None


def test_sync_marks_needs_reauth_on_auth_error(db):
    user = User(id="u1", email="u@example.com", base_currency="EUR")
    acc = Account(id=uuid4(), user_id="u1", name="IBKR", account_type="investment_brokerage", currency="EUR")
    conn = BrokerConnection(id=uuid4(), user_id="u1", account_id=acc.id, provider="ibkr_flex",
                            credentials_encrypted=encrypt({"flex_token": "t", "query_id_positions": "qp", "query_id_trades": "qt"}))
    db.add_all([user, acc, conn]); db.commit()

    from app.integrations.ibkr_flex_adapter import FlexAuthError
    adapter = MagicMock()
    adapter.request_statement.side_effect = FlexAuthError("token bad")
    fx = MagicMock(); fx.convert.side_effect = lambda *a, **kw: Decimal("0")

    svc = InvestmentSyncService(db=db, adapter_factory=lambda creds: adapter, fx=fx)
    with pytest.raises(FlexAuthError):
        svc.sync_account(acc.id, on=date(2026, 4, 18))
    db.refresh(conn)
    assert conn.last_sync_status == "needs_reauth"
    assert "token bad" in (conn.last_sync_error or "")
```

- [ ] **Step 2: Run — expect failure**

Run: `cd backend && pytest tests/test_investment_sync_service.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement**

```python
# backend/app/services/investment_sync_service.py
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Callable
from uuid import UUID
import logging
from sqlalchemy.orm import Session

from app.models import (
    Account, BrokerConnection, Holding, BrokerTrade, PriceSnapshot,
)
from app.services.credentials_crypto import decrypt
from app.services.holding_valuation_service import HoldingValuationService, FxConverter
from app.services.price_service import PriceService
from app.integrations.ibkr_flex_adapter import (
    IBKRFlexAdapter, FlexAuthError, FlexStatementNotReady, FlexError,
)

logger = logging.getLogger(__name__)

AdapterFactory = Callable[[dict], IBKRFlexAdapter]


def _default_factory(creds: dict) -> IBKRFlexAdapter:
    return IBKRFlexAdapter(
        token=creds["flex_token"],
        query_id_positions=creds["query_id_positions"],
        query_id_trades=creds["query_id_trades"],
    )


class InvestmentSyncService:
    def __init__(self, db: Session, fx: FxConverter,
                 adapter_factory: AdapterFactory | None = None,
                 price_service: PriceService | None = None,
                 valuation_service: HoldingValuationService | None = None):
        self.db = db
        self.fx = fx
        self.adapter_factory = adapter_factory or _default_factory
        self.price_service = price_service or PriceService(db=db)
        self.valuation_service = valuation_service or HoldingValuationService(db=db, fx=fx, price_service=self.price_service)

    def sync_account(self, account_id: UUID, on: date | None = None) -> None:
        on = on or date.today()
        account = self.db.query(Account).filter_by(id=account_id).one()
        if account.account_type == "investment_brokerage":
            self._sync_brokerage(account, on)
        elif account.account_type == "investment_manual":
            self._sync_manual(account, on)
        else:
            raise ValueError(f"Account {account_id} is not an investment account")

    # --- Brokerage path ---
    def _sync_brokerage(self, account: Account, on: date) -> None:
        conn = self.db.query(BrokerConnection).filter_by(account_id=account.id).one()
        creds = decrypt(conn.credentials_encrypted)
        adapter = self.adapter_factory(creds)
        try:
            ref_positions = adapter.request_statement(creds["query_id_positions"])
            positions_xml = adapter.fetch_statement(ref_positions)
            ref_trades = adapter.request_statement(creds["query_id_trades"])
            trades_xml = adapter.fetch_statement(ref_trades)
        except FlexAuthError as e:
            conn.last_sync_status = "needs_reauth"
            conn.last_sync_error = str(e)
            self.db.commit()
            raise
        except FlexStatementNotReady:
            conn.last_sync_status = "pending"
            self.db.commit()
            raise
        except FlexError as e:
            conn.last_sync_status = "error"
            conn.last_sync_error = str(e)
            self.db.commit()
            raise

        statement = adapter.parse_positions_xml(positions_xml)
        trades = adapter.parse_trades_xml(trades_xml)
        self._upsert_positions(account, statement.positions)
        self._upsert_cash(account, statement.cash)
        self._upsert_trades(account, trades)
        # Run valuation
        self.valuation_service.compute(account_id=account.id, on=on)

        conn.last_sync_status = "ok"
        conn.last_sync_error = None
        conn.last_sync_at = datetime.utcnow()
        self.db.commit()

    # --- Manual path ---
    def _sync_manual(self, account: Account, on: date) -> None:
        holdings = self.db.query(Holding).filter_by(account_id=account.id).all()
        symbols = sorted({h.symbol for h in holdings if h.instrument_type != "cash"})
        if symbols:
            self.price_service.get_or_fetch(symbols, on)
        self.valuation_service.compute(account_id=account.id, on=on)
        account.last_synced_at = datetime.utcnow()
        self.db.commit()

    # --- Upsert helpers ---
    def _upsert_positions(self, account: Account, positions) -> None:
        seen = set()
        for p in positions:
            seen.add((p.symbol, p.instrument_type))
            row = self.db.query(Holding).filter_by(
                account_id=account.id, symbol=p.symbol, instrument_type=p.instrument_type
            ).one_or_none()
            if row is None:
                row = Holding(
                    user_id=account.user_id, account_id=account.id, symbol=p.symbol,
                    name=p.name, currency=p.currency, instrument_type=p.instrument_type,
                    quantity=p.quantity, avg_cost=p.avg_cost, source="ibkr_flex",
                )
                self.db.add(row)
            else:
                row.quantity = p.quantity
                row.avg_cost = p.avg_cost
                row.name = p.name
                row.currency = p.currency
        # Remove brokerage-source holdings no longer present
        for h in list(self.db.query(Holding).filter_by(account_id=account.id, source="ibkr_flex").all()):
            if (h.symbol, h.instrument_type) not in seen and h.instrument_type != "cash":
                self.db.delete(h)

    def _upsert_cash(self, account: Account, cash) -> None:
        seen = set()
        for c in cash:
            seen.add(c.currency)
            row = self.db.query(Holding).filter_by(
                account_id=account.id, symbol=c.currency, instrument_type="cash"
            ).one_or_none()
            if row is None:
                row = Holding(
                    user_id=account.user_id, account_id=account.id, symbol=c.currency,
                    name=f"Cash ({c.currency})", currency=c.currency,
                    instrument_type="cash", quantity=c.balance, source="ibkr_flex",
                )
                self.db.add(row)
            else:
                row.quantity = c.balance
        for h in self.db.query(Holding).filter_by(account_id=account.id, source="ibkr_flex", instrument_type="cash").all():
            if h.symbol not in seen:
                self.db.delete(h)

    def _upsert_trades(self, account: Account, trades) -> None:
        existing = {
            t.external_id for t in
            self.db.query(BrokerTrade.external_id).filter_by(account_id=account.id).all()
        }
        for t in trades:
            if t.external_id in existing:
                continue
            self.db.add(BrokerTrade(
                account_id=account.id, symbol=t.symbol, trade_date=t.trade_date,
                side=t.side, quantity=t.quantity, price=t.price,
                currency=t.currency, external_id=t.external_id,
            ))
```

- [ ] **Step 4: Run — expect pass**

Run: `cd backend && pytest tests/test_investment_sync_service.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/investment_sync_service.py backend/tests/test_investment_sync_service.py
git commit -m "feat(investments): InvestmentSyncService for brokerage + manual"
```

---

## Phase 5 — Celery tasks & beat

### Task 11: Investment Celery tasks + beat schedule

**Files:**
- Create: `backend/tasks/investment_tasks.py`
- Modify: `backend/celery_app.py`
- Test: `backend/tests/test_investment_tasks.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_investment_tasks.py
from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Account, BrokerConnection, User


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_daily_sync_enumerates_active_accounts_and_fans_out(db, monkeypatch):
    user = User(id="u1", email="u@example.com", base_currency="EUR")
    a1 = Account(id=uuid4(), user_id="u1", name="IBKR", account_type="investment_brokerage", currency="EUR", is_active=True)
    a2 = Account(id=uuid4(), user_id="u1", name="Manual", account_type="investment_manual", currency="EUR", is_active=True)
    a3 = Account(id=uuid4(), user_id="u1", name="Bank", account_type="checking", currency="EUR", is_active=True)
    a4 = Account(id=uuid4(), user_id="u1", name="Old IBKR", account_type="investment_brokerage", currency="EUR", is_active=False)
    db.add_all([user, a1, a2, a3, a4])
    db.add(BrokerConnection(id=uuid4(), user_id="u1", account_id=a1.id, provider="ibkr_flex",
                            credentials_encrypted="x", last_sync_status="ok"))
    db.commit()

    enqueued: list[str] = []
    with patch("tasks.investment_tasks.SessionLocal", return_value=db), \
         patch("tasks.investment_tasks.sync_investment_account.delay", side_effect=lambda aid: enqueued.append(str(aid))):
        from tasks.investment_tasks import daily_investment_sync_all
        daily_investment_sync_all.run()

    assert sorted(enqueued) == sorted([str(a1.id), str(a2.id)])


def test_sync_investment_account_calls_service(db, monkeypatch):
    user = User(id="u1", email="u@example.com", base_currency="EUR")
    acc = Account(id=uuid4(), user_id="u1", name="Manual", account_type="investment_manual", currency="EUR", is_active=True)
    db.add_all([user, acc]); db.commit()

    fake_svc = MagicMock()
    with patch("tasks.investment_tasks.SessionLocal", return_value=db), \
         patch("tasks.investment_tasks.InvestmentSyncService", return_value=fake_svc):
        from tasks.investment_tasks import sync_investment_account
        sync_investment_account.run(str(acc.id))
    fake_svc.sync_account.assert_called_once()
```

- [ ] **Step 2: Run — expect failure**

Run: `cd backend && pytest tests/test_investment_tasks.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement task module**

```python
# backend/tasks/investment_tasks.py
from __future__ import annotations
from datetime import date
import logging
from uuid import UUID
from celery import shared_task

from app.database import SessionLocal
from app.models import Account, BrokerConnection
from app.services.investment_sync_service import InvestmentSyncService
from app.services.exchange_rate_service import ExchangeRateService
from app.integrations.ibkr_flex_adapter import FlexStatementNotReady

logger = logging.getLogger(__name__)


class _FxAdapter:
    """Adapts ExchangeRateService to the FxConverter protocol."""
    def __init__(self, db):
        self.svc = ExchangeRateService(db=db) if hasattr(ExchangeRateService, "__call__") else None
        # Fallback: most existing services accept `db` kwarg; if not, use as static module.
        self.db = db

    def convert(self, amount, src, dst, on):
        if src.upper() == dst.upper():
            return amount
        # Use whichever method the existing service exposes; this codebase has `convert_amount`.
        from app.services.exchange_rate_service import ExchangeRateService as ERS
        return ERS().convert_amount(amount=amount, from_currency=src, to_currency=dst, on=on, db=self.db)  # type: ignore


@shared_task(name="tasks.investment_tasks.daily_investment_sync_all")
def daily_investment_sync_all() -> dict:
    db = SessionLocal()
    try:
        # Active brokerage accounts that have a non-deleted connection
        broker_account_ids = [
            a.id for a in db.query(Account)
            .join(BrokerConnection, BrokerConnection.account_id == Account.id)
            .filter(Account.is_active == True, Account.account_type == "investment_brokerage")
            .all()
        ]
        manual_account_ids = [
            a.id for a in db.query(Account)
            .filter(Account.is_active == True, Account.account_type == "investment_manual")
            .all()
        ]
        all_ids = list(broker_account_ids) + list(manual_account_ids)
        for aid in all_ids:
            sync_investment_account.delay(str(aid))
        return {"queued": len(all_ids)}
    finally:
        db.close()


@shared_task(
    name="tasks.investment_tasks.sync_investment_account",
    bind=True,
    autoretry_for=(FlexStatementNotReady,),
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=True,
    max_retries=6,
)
def sync_investment_account(self, account_id: str) -> dict:
    db = SessionLocal()
    try:
        svc = InvestmentSyncService(db=db, fx=_FxAdapter(db))
        svc.sync_account(UUID(account_id))
        return {"account_id": account_id, "status": "ok"}
    except FlexStatementNotReady:
        # Celery autoretry handles backoff
        raise
    except Exception as e:
        logger.exception("Investment sync failed for %s: %s", account_id, e)
        return {"account_id": account_id, "status": "error", "error": str(e)}
    finally:
        db.close()
```

- [ ] **Step 4: Wire into Celery beat**

Edit `backend/celery_app.py`:
- Add `"tasks.investment_tasks"` to the `include=[...]` list in the `Celery(...)` call.
- Inside `_build_beat_schedule`, append:

```python
investment_hour = int(os.getenv("SYLLOGIC_INVESTMENT_SYNC_HOUR_UTC", "2"))
investment_hour = max(0, min(23, investment_hour))
schedule["daily-investment-sync-all"] = {
    "task": "tasks.investment_tasks.daily_investment_sync_all",
    "schedule": crontab(minute=0, hour=investment_hour),
}
```

- [ ] **Step 5: Run — expect pass**

Run: `cd backend && pytest tests/test_investment_tasks.py -v`
Expected: 2 PASS.

> Note: if `ExchangeRateService.convert_amount` doesn't exist by that name, inspect `backend/app/services/exchange_rate_service.py` and use the equivalent method (e.g. `get_rate` + multiply). Adjust `_FxAdapter.convert` accordingly. The contract: `convert(amount, src, dst, on) -> Decimal`.

- [ ] **Step 6: Commit**

```bash
git add backend/tasks/investment_tasks.py backend/celery_app.py backend/tests/test_investment_tasks.py
git commit -m "feat(investments): celery tasks + daily 02:00 UTC beat schedule"
```

---

## Phase 6 — REST API

### Task 12: Pydantic schemas

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Append investment schemas**

```python
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class BrokerConnectionCreate(BaseModel):
    provider: Literal["ibkr_flex"]
    flex_token: str
    query_id_positions: str
    query_id_trades: str
    account_name: str
    base_currency: str = "EUR"


class BrokerConnectionResponse(BaseModel):
    id: UUID
    account_id: UUID
    provider: str
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    last_sync_error: Optional[str]


class ManualAccountCreate(BaseModel):
    name: str
    base_currency: str = "EUR"


class HoldingCreate(BaseModel):
    symbol: str
    quantity: Decimal
    instrument_type: Literal["equity", "etf", "cash"]
    currency: str
    as_of_date: Optional[date] = None
    avg_cost: Optional[Decimal] = None


class HoldingUpdate(BaseModel):
    quantity: Optional[Decimal] = None
    as_of_date: Optional[date] = None
    avg_cost: Optional[Decimal] = None


class HoldingResponse(BaseModel):
    id: UUID
    account_id: UUID
    symbol: str
    name: Optional[str]
    currency: str
    instrument_type: str
    quantity: Decimal
    avg_cost: Optional[Decimal]
    as_of_date: Optional[date]
    source: str
    current_price: Optional[Decimal] = None
    current_value_user_currency: Optional[Decimal] = None
    is_stale: bool = False


class PortfolioSummary(BaseModel):
    total_value: Decimal
    total_value_today_change: Decimal
    currency: str
    accounts: list[dict]
    allocation_by_type: dict[str, Decimal]
    allocation_by_currency: dict[str, Decimal]


class ValuationPoint(BaseModel):
    date: date
    value: Decimal


class SymbolSearchResult(BaseModel):
    symbol: str
    name: str
    exchange: Optional[str] = None
    currency: Optional[str] = None
```

- [ ] **Step 2: Type-check**

Run: `cd backend && python -c "from app.schemas import HoldingResponse, PortfolioSummary; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(investments): pydantic schemas for investment endpoints"
```

---

### Task 13: Investment routes — connections + manual flows

**Files:**
- Create: `backend/app/routes/investments.py`
- Modify: `backend/app/routes/__init__.py`
- Test: `backend/tests/test_investments_routes.py`

- [ ] **Step 1: Write the failing test (FastAPI TestClient)**

```python
# backend/tests/test_investments_routes.py
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.main import app
from app.models import User, Account, Holding


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def client(db, monkeypatch):
    from app.services import credentials_crypto
    monkeypatch.setenv("SYLLOGIC_SECRET_KEY", credentials_crypto.generate_key())
    db.add(User(id="u1", email="u@example.com", base_currency="EUR")); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    monkeypatch.setattr("app.db_helpers.get_user_id", lambda x=None: "u1")
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_manual_account_and_holding(client, db):
    r = client.post("/api/investments/manual-accounts", json={"name": "Etoro", "base_currency": "EUR"})
    assert r.status_code == 200
    account_id = r.json()["account_id"]

    with patch("app.routes.investments.get_price_provider") as gp:
        provider = gp.return_value
        provider.search_symbols.return_value = [
            type("S", (), {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ", "currency": "USD"})()
        ]
        r = client.post(
            f"/api/investments/manual-accounts/{account_id}/holdings",
            json={"symbol": "AAPL", "quantity": "10", "instrument_type": "equity",
                  "currency": "USD", "as_of_date": "2026-04-01"},
        )
    assert r.status_code == 200, r.text
    holdings = db.query(Holding).all()
    assert holdings[0].symbol == "AAPL"
    assert holdings[0].source == "manual"


def test_create_broker_connection_encrypts_credentials(client, db):
    with patch("app.routes.investments.sync_investment_account") as task:
        r = client.post("/api/investments/broker-connections", json={
            "provider": "ibkr_flex", "flex_token": "TOKEN_X",
            "query_id_positions": "111", "query_id_trades": "222",
            "account_name": "IBKR", "base_currency": "EUR",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "connection_id" in body and "account_id" in body
    from app.models import BrokerConnection
    conn = db.query(BrokerConnection).one()
    assert "TOKEN_X" not in conn.credentials_encrypted
    task.delay.assert_called_once()


def test_delete_holding_only_for_manual(client, db):
    acc = Account(id=uuid4(), user_id="u1", name="m", account_type="investment_manual", currency="EUR")
    h = Holding(id=uuid4(), user_id="u1", account_id=acc.id, symbol="AAPL", currency="USD",
                instrument_type="equity", quantity=Decimal("1"), source="ibkr_flex")
    db.add_all([acc, h]); db.commit()
    r = client.delete(f"/api/investments/holdings/{h.id}")
    assert r.status_code == 400
    h.source = "manual"; db.commit()
    r = client.delete(f"/api/investments/holdings/{h.id}")
    assert r.status_code == 204
```

- [ ] **Step 2: Run — expect failure**

Run: `cd backend && pytest tests/test_investments_routes.py -v`
Expected: failure (router not registered / file missing).

- [ ] **Step 3: Implement routes**

```python
# backend/app/routes/investments.py
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_helpers import get_user_id
from app.models import (
    Account, BrokerConnection, Holding, HoldingValuation, AccountBalance,
)
from app.schemas import (
    BrokerConnectionCreate, BrokerConnectionResponse,
    ManualAccountCreate, HoldingCreate, HoldingUpdate, HoldingResponse,
    PortfolioSummary, ValuationPoint, SymbolSearchResult,
)
from app.services.credentials_crypto import encrypt
from app.integrations.price_provider import get_price_provider
from tasks.investment_tasks import sync_investment_account

router = APIRouter(prefix="/investments")


def _account_for_user(db: Session, account_id: UUID, user_id: str) -> Account:
    acc = db.query(Account).filter_by(id=account_id, user_id=user_id).one_or_none()
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return acc


# ---------- Broker connections ----------

@router.post("/broker-connections")
def create_broker_connection(payload: BrokerConnectionCreate, user_id: Optional[str] = None,
                             db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    account = Account(user_id=user_id, name=payload.account_name,
                      account_type="investment_brokerage", currency=payload.base_currency,
                      provider="ibkr_flex", is_active=True)
    db.add(account); db.flush()
    conn = BrokerConnection(
        user_id=user_id, account_id=account.id, provider=payload.provider,
        credentials_encrypted=encrypt({
            "flex_token": payload.flex_token,
            "query_id_positions": payload.query_id_positions,
            "query_id_trades": payload.query_id_trades,
        }),
    )
    db.add(conn); db.commit()
    task = sync_investment_account.delay(str(account.id))
    return {"connection_id": str(conn.id), "account_id": str(account.id), "sync_task_id": task.id if hasattr(task, "id") else None}


@router.get("/broker-connections", response_model=List[BrokerConnectionResponse])
def list_broker_connections(user_id: Optional[str] = None, db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    rows = db.query(BrokerConnection).filter_by(user_id=user_id).all()
    return [BrokerConnectionResponse(
        id=c.id, account_id=c.account_id, provider=c.provider,
        last_sync_at=c.last_sync_at, last_sync_status=c.last_sync_status, last_sync_error=c.last_sync_error,
    ) for c in rows]


@router.post("/broker-connections/{connection_id}/sync")
def trigger_sync(connection_id: UUID, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    conn = db.query(BrokerConnection).filter_by(id=connection_id, user_id=user_id).one_or_none()
    if conn is None:
        raise HTTPException(404, "Connection not found")
    task = sync_investment_account.delay(str(conn.account_id))
    return {"sync_task_id": getattr(task, "id", None)}


@router.delete("/broker-connections/{connection_id}", status_code=204)
def delete_broker_connection(connection_id: UUID, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    conn = db.query(BrokerConnection).filter_by(id=connection_id, user_id=user_id).one_or_none()
    if conn is None:
        raise HTTPException(404)
    acc = db.query(Account).filter_by(id=conn.account_id).one()
    acc.is_active = False
    db.delete(conn); db.commit()
    return None


# ---------- Manual accounts ----------

@router.post("/manual-accounts")
def create_manual_account(payload: ManualAccountCreate, user_id: Optional[str] = None,
                          db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    acc = Account(user_id=user_id, name=payload.name, account_type="investment_manual",
                  currency=payload.base_currency, is_active=True)
    db.add(acc); db.commit()
    return {"account_id": str(acc.id)}


@router.post("/manual-accounts/{account_id}/holdings")
def add_manual_holding(account_id: UUID, payload: HoldingCreate, user_id: Optional[str] = None,
                       db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    acc = _account_for_user(db, account_id, user_id)
    if acc.account_type != "investment_manual":
        raise HTTPException(400, "Holdings can only be added to manual accounts")
    if payload.instrument_type != "cash":
        provider = get_price_provider()
        matches = provider.search_symbols(payload.symbol)
        if not any(getattr(m, "symbol", "") == payload.symbol for m in matches):
            raise HTTPException(422, f"Unknown symbol {payload.symbol}")
    h = Holding(
        user_id=user_id, account_id=acc.id, symbol=payload.symbol,
        currency=payload.currency, instrument_type=payload.instrument_type,
        quantity=payload.quantity, avg_cost=payload.avg_cost,
        as_of_date=payload.as_of_date, source="manual",
    )
    db.add(h); db.commit()
    sync_investment_account.delay(str(acc.id))
    return {"holding_id": str(h.id)}


@router.patch("/holdings/{holding_id}")
def update_holding(holding_id: UUID, payload: HoldingUpdate, user_id: Optional[str] = None,
                   db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    h = db.query(Holding).filter_by(id=holding_id, user_id=user_id).one_or_none()
    if h is None:
        raise HTTPException(404)
    if h.source != "manual":
        raise HTTPException(400, "Only manual holdings can be edited")
    if payload.quantity is not None: h.quantity = payload.quantity
    if payload.as_of_date is not None: h.as_of_date = payload.as_of_date
    if payload.avg_cost is not None: h.avg_cost = payload.avg_cost
    db.commit()
    return {"ok": True}


@router.delete("/holdings/{holding_id}", status_code=204)
def delete_holding(holding_id: UUID, user_id: Optional[str] = None, db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    h = db.query(Holding).filter_by(id=holding_id, user_id=user_id).one_or_none()
    if h is None:
        raise HTTPException(404)
    if h.source != "manual":
        raise HTTPException(400, "Only manual holdings can be deleted")
    db.delete(h); db.commit()
    return None


# ---------- Read endpoints ----------

@router.get("/holdings", response_model=List[HoldingResponse])
def list_holdings(account_id: Optional[UUID] = None, user_id: Optional[str] = None,
                  db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    q = db.query(Holding).filter_by(user_id=user_id)
    if account_id is not None:
        q = q.filter_by(account_id=account_id)
    out = []
    for h in q.all():
        latest = (db.query(HoldingValuation)
                  .filter_by(holding_id=h.id)
                  .order_by(HoldingValuation.date.desc())
                  .first())
        out.append(HoldingResponse(
            id=h.id, account_id=h.account_id, symbol=h.symbol, name=h.name,
            currency=h.currency, instrument_type=h.instrument_type,
            quantity=h.quantity, avg_cost=h.avg_cost, as_of_date=h.as_of_date, source=h.source,
            current_price=(latest.price if latest else None),
            current_value_user_currency=(latest.value_user_currency if latest else None),
            is_stale=(bool(latest.is_stale) if latest else False),
        ))
    return out


@router.get("/holdings/{holding_id}/history", response_model=List[ValuationPoint])
def holding_history(holding_id: UUID, from_: date = Query(..., alias="from"), to: date = Query(...),
                    user_id: Optional[str] = None, db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    h = db.query(Holding).filter_by(id=holding_id, user_id=user_id).one_or_none()
    if h is None:
        raise HTTPException(404)
    rows = (db.query(HoldingValuation)
            .filter(HoldingValuation.holding_id == h.id,
                    HoldingValuation.date >= from_, HoldingValuation.date <= to)
            .order_by(HoldingValuation.date).all())
    return [ValuationPoint(date=r.date, value=r.value_user_currency) for r in rows]


@router.get("/portfolio", response_model=PortfolioSummary)
def portfolio_summary(user_id: Optional[str] = None, db: Session = Depends(get_db)):
    from app.models import User as UserModel
    user_id = get_user_id(user_id)
    user = db.query(UserModel).filter_by(id=user_id).one()
    inv_accounts = db.query(Account).filter(
        Account.user_id == user_id, Account.is_active == True,
        Account.account_type.in_(["investment_brokerage", "investment_manual"]),
    ).all()
    total = sum((Decimal(a.balance_available or 0) for a in inv_accounts), start=Decimal("0"))

    # Today change: last balance vs previous balance per account
    today_change = Decimal("0")
    for a in inv_accounts:
        last_two = (db.query(AccountBalance)
                    .filter_by(account_id=a.id)
                    .order_by(AccountBalance.date.desc()).limit(2).all())
        if len(last_two) == 2:
            today_change += Decimal(last_two[0].balance) - Decimal(last_two[1].balance)

    # Allocation breakdowns
    from collections import defaultdict
    by_type: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_currency: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for h in db.query(Holding).filter(Holding.account_id.in_([a.id for a in inv_accounts])).all():
        latest = (db.query(HoldingValuation)
                  .filter_by(holding_id=h.id).order_by(HoldingValuation.date.desc()).first())
        if latest is None:
            continue
        by_type[h.instrument_type] += Decimal(latest.value_user_currency)
        by_currency[h.currency] += Decimal(latest.value_user_currency)

    return PortfolioSummary(
        total_value=total,
        total_value_today_change=today_change,
        currency=getattr(user, "base_currency", "EUR") or "EUR",
        accounts=[{"id": str(a.id), "name": a.name, "balance": a.balance_available or 0,
                   "type": a.account_type} for a in inv_accounts],
        allocation_by_type=dict(by_type),
        allocation_by_currency=dict(by_currency),
    )


@router.get("/portfolio/history", response_model=List[ValuationPoint])
def portfolio_history(from_: date = Query(..., alias="from"), to: date = Query(...),
                      user_id: Optional[str] = None, db: Session = Depends(get_db)):
    user_id = get_user_id(user_id)
    inv_accounts = db.query(Account).filter(
        Account.user_id == user_id,
        Account.account_type.in_(["investment_brokerage", "investment_manual"]),
    ).all()
    by_date: dict[date, Decimal] = {}
    for a in inv_accounts:
        rows = (db.query(AccountBalance)
                .filter(AccountBalance.account_id == a.id,
                        AccountBalance.date >= from_, AccountBalance.date <= to).all())
        for r in rows:
            by_date[r.date] = by_date.get(r.date, Decimal("0")) + Decimal(r.balance)
    return [ValuationPoint(date=d, value=v) for d, v in sorted(by_date.items())]


@router.get("/symbols/search", response_model=List[SymbolSearchResult])
def symbol_search(q: str = Query(..., min_length=1)):
    provider = get_price_provider()
    matches = provider.search_symbols(q)
    return [SymbolSearchResult(symbol=m.symbol, name=m.name,
                               exchange=getattr(m, "exchange", None),
                               currency=getattr(m, "currency", None)) for m in matches]
```

- [ ] **Step 4: Register router**

Edit `backend/app/routes/__init__.py` — import the new router and include it under `/api`:

```python
from .investments import router as investments_router
api_router.include_router(investments_router, prefix="/api", tags=["investments"])
```

- [ ] **Step 5: Run — expect pass**

Run: `cd backend && pytest tests/test_investments_routes.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/investments.py backend/app/routes/__init__.py backend/tests/test_investments_routes.py
git commit -m "feat(investments): REST endpoints for connections, holdings, portfolio"
```

---

## Phase 7 — MCP tools

### Task 14: MCP investments tools

**Files:**
- Create: `backend/app/mcp/tools/investments.py`
- Modify: `backend/app/mcp/server.py` (or `tools/__init__.py`) to register the new tool module
- Test: `backend/tests/test_mcp_investments_tools.py`

- [ ] **Step 1: Inspect an existing tool file for the registration pattern**

Run: `cd backend && head -40 app/mcp/tools/accounts.py`

Expected: shows the FastMCP tool decorator pattern (e.g. `@mcp.tool()` or registration via a registry function).

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_mcp_investments_tools.py
from datetime import date
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import (
    User, Account, Holding, HoldingValuation, BrokerConnection,
)
from app.mcp.tools import investments as inv_tools


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_list_holdings_returns_per_account_holdings(db):
    user = User(id="u1", email="u@example.com", base_currency="EUR")
    acc = Account(id=uuid4(), user_id="u1", name="m", account_type="investment_manual", currency="EUR", balance_available=Decimal("2199.07"))
    h = Holding(id=uuid4(), user_id="u1", account_id=acc.id, symbol="AAPL",
                currency="USD", instrument_type="equity", quantity=Decimal("10"), source="manual")
    db.add_all([user, acc, h])
    db.add(HoldingValuation(holding_id=h.id, date=date(2026, 4, 18),
                            quantity=Decimal("10"), price=Decimal("234.56"),
                            value_user_currency=Decimal("2199.07"), is_stale=False))
    db.commit()
    out = inv_tools.list_holdings_impl(db=db, user_id="u1")
    assert len(out) == 1
    assert out[0]["symbol"] == "AAPL"
    assert out[0]["current_value_user_currency"] == "2199.07"


def test_get_portfolio_summary_aggregates(db):
    user = User(id="u1", email="u@example.com", base_currency="EUR")
    a1 = Account(id=uuid4(), user_id="u1", name="m", account_type="investment_manual", currency="EUR", balance_available=Decimal("100"), is_active=True)
    a2 = Account(id=uuid4(), user_id="u1", name="b", account_type="investment_brokerage", currency="EUR", balance_available=Decimal("200"), is_active=True)
    db.add_all([user, a1, a2]); db.commit()
    out = inv_tools.get_portfolio_summary_impl(db=db, user_id="u1")
    assert out["total_value"] == "300.00" or out["total_value"] == "300"
```

- [ ] **Step 3: Run — expect failure**

Run: `cd backend && pytest tests/test_mcp_investments_tools.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement tool module (pure functions + MCP wrappers)**

```python
# backend/app/mcp/tools/investments.py
"""MCP tools for the investments feature. Read-only in v1."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Account, Holding, HoldingValuation, BrokerConnection, AccountBalance, User,
)


def _str_dec(d: Decimal | None) -> str | None:
    if d is None:
        return None
    return str(Decimal(d))


def list_holdings_impl(*, db: Session, user_id: str, account_id: Optional[str] = None) -> list[dict]:
    q = db.query(Holding).filter_by(user_id=user_id)
    if account_id:
        q = q.filter_by(account_id=account_id)
    out = []
    for h in q.all():
        latest = (db.query(HoldingValuation).filter_by(holding_id=h.id)
                  .order_by(HoldingValuation.date.desc()).first())
        out.append({
            "id": str(h.id),
            "account_id": str(h.account_id),
            "symbol": h.symbol,
            "name": h.name,
            "currency": h.currency,
            "instrument_type": h.instrument_type,
            "quantity": _str_dec(h.quantity),
            "current_price": _str_dec(latest.price if latest else None),
            "current_value_user_currency": _str_dec(latest.value_user_currency if latest else None),
            "is_stale": bool(latest.is_stale) if latest else False,
            "source": h.source,
        })
    return out


def get_portfolio_summary_impl(*, db: Session, user_id: str) -> dict:
    user = db.query(User).filter_by(id=user_id).one()
    inv = db.query(Account).filter(
        Account.user_id == user_id, Account.is_active == True,
        Account.account_type.in_(["investment_brokerage", "investment_manual"]),
    ).all()
    total = sum((Decimal(a.balance_available or 0) for a in inv), start=Decimal("0"))
    return {
        "total_value": str(total),
        "currency": getattr(user, "base_currency", "EUR") or "EUR",
        "account_count": len(inv),
    }


def get_holding_impl(*, db: Session, user_id: str, holding_id: str) -> dict | None:
    h = db.query(Holding).filter_by(id=holding_id, user_id=user_id).one_or_none()
    if h is None:
        return None
    latest = (db.query(HoldingValuation).filter_by(holding_id=h.id)
              .order_by(HoldingValuation.date.desc()).first())
    return {
        "id": str(h.id), "symbol": h.symbol, "name": h.name,
        "quantity": _str_dec(h.quantity), "avg_cost": _str_dec(h.avg_cost),
        "currency": h.currency, "instrument_type": h.instrument_type,
        "current_price": _str_dec(latest.price if latest else None),
        "current_value_user_currency": _str_dec(latest.value_user_currency if latest else None),
        "as_of_date": h.as_of_date.isoformat() if h.as_of_date else None,
        "source": h.source,
    }


def get_holding_history_impl(*, db: Session, user_id: str, holding_id: str,
                             from_: date, to: date) -> list[dict]:
    h = db.query(Holding).filter_by(id=holding_id, user_id=user_id).one_or_none()
    if h is None:
        return []
    rows = (db.query(HoldingValuation)
            .filter(HoldingValuation.holding_id == h.id,
                    HoldingValuation.date >= from_, HoldingValuation.date <= to)
            .order_by(HoldingValuation.date).all())
    return [{"date": r.date.isoformat(), "value": _str_dec(r.value_user_currency)} for r in rows]


def get_portfolio_history_impl(*, db: Session, user_id: str, from_: date, to: date) -> list[dict]:
    inv = db.query(Account).filter(
        Account.user_id == user_id,
        Account.account_type.in_(["investment_brokerage", "investment_manual"]),
    ).all()
    by_date: dict[date, Decimal] = {}
    for a in inv:
        rows = (db.query(AccountBalance)
                .filter(AccountBalance.account_id == a.id,
                        AccountBalance.date >= from_, AccountBalance.date <= to).all())
        for r in rows:
            by_date[r.date] = by_date.get(r.date, Decimal("0")) + Decimal(r.balance)
    return [{"date": d.isoformat(), "value": str(v)} for d, v in sorted(by_date.items())]


def list_broker_connections_impl(*, db: Session, user_id: str) -> list[dict]:
    rows = db.query(BrokerConnection).filter_by(user_id=user_id).all()
    return [{
        "id": str(c.id), "account_id": str(c.account_id), "provider": c.provider,
        "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
        "last_sync_status": c.last_sync_status,
        "last_sync_error": c.last_sync_error,
    } for c in rows]


def search_symbols_impl(*, query: str) -> list[dict]:
    from app.integrations.price_provider import get_price_provider
    matches = get_price_provider().search_symbols(query)
    return [{"symbol": m.symbol, "name": m.name,
             "exchange": getattr(m, "exchange", None),
             "currency": getattr(m, "currency", None)} for m in matches]


# ---- MCP registration ----
def register(mcp, get_session=SessionLocal, get_user_id=lambda: None):
    """Wire the *_impl functions into the FastMCP server with the existing auth plumbing.
    Adapt to whatever pattern other tool modules in `app/mcp/tools/*.py` use — see e.g. `accounts.py`.
    """
    @mcp.tool()
    def list_holdings(account_id: Optional[str] = None, user_id: Optional[str] = None) -> list[dict]:
        with get_session() as db:
            uid = user_id or get_user_id()
            return list_holdings_impl(db=db, user_id=uid, account_id=account_id)

    @mcp.tool()
    def get_portfolio_summary(user_id: Optional[str] = None) -> dict:
        with get_session() as db:
            uid = user_id or get_user_id()
            return get_portfolio_summary_impl(db=db, user_id=uid)

    @mcp.tool()
    def get_holding(holding_id: str, user_id: Optional[str] = None) -> dict | None:
        with get_session() as db:
            uid = user_id or get_user_id()
            return get_holding_impl(db=db, user_id=uid, holding_id=holding_id)

    @mcp.tool()
    def get_holding_history(holding_id: str, from_: str, to: str, user_id: Optional[str] = None) -> list[dict]:
        with get_session() as db:
            uid = user_id or get_user_id()
            return get_holding_history_impl(db=db, user_id=uid, holding_id=holding_id,
                                            from_=date.fromisoformat(from_), to=date.fromisoformat(to))

    @mcp.tool()
    def get_portfolio_history(from_: str, to: str, user_id: Optional[str] = None) -> list[dict]:
        with get_session() as db:
            uid = user_id or get_user_id()
            return get_portfolio_history_impl(db=db, user_id=uid,
                                              from_=date.fromisoformat(from_), to=date.fromisoformat(to))

    @mcp.tool()
    def list_broker_connections(user_id: Optional[str] = None) -> list[dict]:
        with get_session() as db:
            uid = user_id or get_user_id()
            return list_broker_connections_impl(db=db, user_id=uid)

    @mcp.tool()
    def search_symbols(query: str) -> list[dict]:
        return search_symbols_impl(query=query)
```

- [ ] **Step 5: Register the module on the MCP server**

Look at `backend/app/mcp/server.py` (and how `accounts.py`/`transactions.py` are wired). Add the parallel call for `investments`. If the existing pattern is `from app.mcp.tools import accounts; accounts.register(mcp, ...)`, replicate it.

Run: `cd backend && grep -n register app/mcp/server.py app/mcp/tools/__init__.py 2>/dev/null`
Use whatever pattern already exists; if tools self-register on import, just import the module from `app/mcp/server.py`.

- [ ] **Step 6: Run — expect pass**

Run: `cd backend && pytest tests/test_mcp_investments_tools.py -v`
Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/mcp/tools/investments.py backend/app/mcp/server.py backend/tests/test_mcp_investments_tools.py
git commit -m "feat(investments): MCP tools for portfolio + holdings + symbol search"
```

---

## Phase 8 — Frontend

> Each frontend task ends with a `pnpm tsc --noEmit && pnpm lint` check and commit. There are no unit tests required for v1 frontend; the backend integration is the contract.

### Task 15: Typed API client

**Files:**
- Create: `frontend/lib/api/investments.ts`

- [ ] **Step 1: Implement client**

```ts
// frontend/lib/api/investments.ts
import { backendUrl } from "@/lib/backend-url";

export type Holding = {
  id: string;
  account_id: string;
  symbol: string;
  name: string | null;
  currency: string;
  instrument_type: "equity" | "etf" | "cash";
  quantity: string;
  avg_cost?: string | null;
  as_of_date?: string | null;
  source: "manual" | "ibkr_flex";
  current_price?: string | null;
  current_value_user_currency?: string | null;
  is_stale: boolean;
};

export type PortfolioSummary = {
  total_value: string;
  total_value_today_change: string;
  currency: string;
  accounts: Array<{ id: string; name: string; balance: string | number; type: string }>;
  allocation_by_type: Record<string, string>;
  allocation_by_currency: Record<string, string>;
};

export type ValuationPoint = { date: string; value: string };

export type SymbolSearchResult = {
  symbol: string;
  name: string;
  exchange?: string | null;
  currency?: string | null;
};

const base = () => `${backendUrl()}/api/investments`;

export async function listHoldings(accountId?: string): Promise<Holding[]> {
  const url = new URL(`${base()}/holdings`);
  if (accountId) url.searchParams.set("account_id", accountId);
  return (await fetch(url.toString(), { credentials: "include" })).json();
}

export async function getPortfolio(): Promise<PortfolioSummary> {
  return (await fetch(`${base()}/portfolio`, { credentials: "include" })).json();
}

export async function getPortfolioHistory(from: string, to: string): Promise<ValuationPoint[]> {
  return (await fetch(`${base()}/portfolio/history?from=${from}&to=${to}`, { credentials: "include" })).json();
}

export async function searchSymbols(q: string): Promise<SymbolSearchResult[]> {
  return (await fetch(`${base()}/symbols/search?q=${encodeURIComponent(q)}`, { credentials: "include" })).json();
}

export async function createBrokerConnection(payload: {
  provider: "ibkr_flex"; flex_token: string; query_id_positions: string;
  query_id_trades: string; account_name: string; base_currency: string;
}): Promise<{ connection_id: string; account_id: string }> {
  const r = await fetch(`${base()}/broker-connections`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function createManualAccount(name: string, base_currency: string): Promise<{ account_id: string }> {
  const r = await fetch(`${base()}/manual-accounts`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, base_currency }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function addManualHolding(accountId: string, payload: {
  symbol: string; quantity: string; instrument_type: "equity" | "etf" | "cash";
  currency: string; as_of_date?: string; avg_cost?: string;
}): Promise<{ holding_id: string }> {
  const r = await fetch(`${base()}/manual-accounts/${accountId}/holdings`, {
    method: "POST", credentials: "include",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

export async function deleteHolding(holdingId: string): Promise<void> {
  await fetch(`${base()}/holdings/${holdingId}`, { method: "DELETE", credentials: "include" });
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && pnpm tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api/investments.ts
git commit -m "feat(investments): typed frontend API client"
```

---

### Task 16: Investments overview page + components

**Files:**
- Create: `frontend/app/(dashboard)/investments/page.tsx`
- Create: `frontend/components/investments/HoldingsTable.tsx`
- Create: `frontend/components/investments/AllocationChart.tsx`

- [ ] **Step 1: Implement `HoldingsTable.tsx`**

```tsx
// frontend/components/investments/HoldingsTable.tsx
"use client";
import { Holding } from "@/lib/api/investments";

export function HoldingsTable({ holdings, onDelete }: {
  holdings: Holding[];
  onDelete?: (id: string) => void;
}) {
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-muted-foreground">
        <tr><th>Symbol</th><th>Type</th><th className="text-right">Qty</th><th className="text-right">Price</th><th className="text-right">Value</th><th /></tr>
      </thead>
      <tbody>
        {holdings.map(h => (
          <tr key={h.id} className="border-t">
            <td className="py-2"><span className="font-medium">{h.symbol}</span> <span className="text-xs text-muted-foreground">{h.name}</span></td>
            <td>{h.instrument_type}</td>
            <td className="text-right">{h.quantity}</td>
            <td className="text-right">{h.current_price ?? "—"} {h.currency}</td>
            <td className={`text-right ${h.is_stale ? "text-amber-600" : ""}`}>{h.current_value_user_currency ?? "—"}</td>
            <td className="text-right">
              {onDelete && h.source === "manual" && (
                <button className="text-xs text-red-600" onClick={() => onDelete(h.id)}>Remove</button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Implement `AllocationChart.tsx`** (use whatever chart lib the project already uses — `grep -l recharts frontend/components` to confirm; if none found, render a simple legend table instead)

```tsx
// frontend/components/investments/AllocationChart.tsx
"use client";
export function AllocationChart({ allocation }: { allocation: Record<string, string> }) {
  const total = Object.values(allocation).reduce((s, v) => s + Number(v), 0);
  return (
    <ul className="space-y-1 text-sm">
      {Object.entries(allocation).map(([k, v]) => {
        const pct = total ? (Number(v) / total) * 100 : 0;
        return (
          <li key={k} className="flex justify-between gap-2">
            <span className="capitalize">{k}</span>
            <span>{pct.toFixed(1)}% · {v}</span>
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 3: Implement page**

```tsx
// frontend/app/(dashboard)/investments/page.tsx
import { getPortfolio, listHoldings } from "@/lib/api/investments";
import { HoldingsTable } from "@/components/investments/HoldingsTable";
import { AllocationChart } from "@/components/investments/AllocationChart";
import Link from "next/link";

export const dynamic = "force-dynamic";

export default async function InvestmentsPage() {
  const [portfolio, holdings] = await Promise.all([getPortfolio(), listHoldings()]);
  return (
    <div className="space-y-6 p-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Investments</h1>
          <p className="text-3xl mt-2">{portfolio.total_value} {portfolio.currency}</p>
          <p className={`text-sm ${Number(portfolio.total_value_today_change) >= 0 ? "text-green-600" : "text-red-600"}`}>
            {portfolio.total_value_today_change} today
          </p>
        </div>
        <Link className="rounded bg-primary text-primary-foreground px-3 py-2 text-sm" href="/investments/connect">
          Add account
        </Link>
      </header>
      <section className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div><h2 className="font-medium mb-2">By type</h2><AllocationChart allocation={portfolio.allocation_by_type} /></div>
        <div><h2 className="font-medium mb-2">By currency</h2><AllocationChart allocation={portfolio.allocation_by_currency} /></div>
      </section>
      <section>
        <h2 className="font-medium mb-2">Holdings</h2>
        <HoldingsTable holdings={holdings} />
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Type-check + lint**

Run: `cd frontend && pnpm tsc --noEmit && pnpm lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(dashboard\)/investments/page.tsx frontend/components/investments/HoldingsTable.tsx frontend/components/investments/AllocationChart.tsx
git commit -m "feat(investments): overview page with allocation + holdings"
```

---

### Task 17: Per-holding detail page

**Files:**
- Create: `frontend/app/(dashboard)/investments/[holdingId]/page.tsx`

- [ ] **Step 1: Implement page**

```tsx
// frontend/app/(dashboard)/investments/[holdingId]/page.tsx
import { backendUrl } from "@/lib/backend-url";

export const dynamic = "force-dynamic";

async function getHistory(id: string) {
  const today = new Date().toISOString().slice(0, 10);
  const oneYearAgo = new Date(Date.now() - 365 * 86400e3).toISOString().slice(0, 10);
  const r = await fetch(`${backendUrl()}/api/investments/holdings/${id}/history?from=${oneYearAgo}&to=${today}`, { credentials: "include" });
  return r.ok ? r.json() : [];
}

export default async function HoldingDetailPage({ params }: { params: Promise<{ holdingId: string }> }) {
  const { holdingId } = await params;
  const history = await getHistory(holdingId);
  return (
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-semibold">Holding history</h1>
      <table className="w-full text-sm">
        <thead><tr className="text-left text-muted-foreground"><th>Date</th><th className="text-right">Value</th></tr></thead>
        <tbody>
          {history.map((p: { date: string; value: string }) => (
            <tr key={p.date} className="border-t"><td className="py-1">{p.date}</td><td className="text-right">{p.value}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Type-check + commit**

```bash
cd frontend && pnpm tsc --noEmit && pnpm lint
git add frontend/app/\(dashboard\)/investments/\[holdingId\]/page.tsx
git commit -m "feat(investments): per-holding history page"
```

---

### Task 18: Connect wizard

**Files:**
- Create: `frontend/app/(dashboard)/investments/connect/page.tsx`
- Create: `frontend/components/investments/ConnectIBKRForm.tsx`
- Create: `frontend/components/investments/AddManualHoldingForm.tsx`

- [ ] **Step 1: `ConnectIBKRForm.tsx`**

```tsx
// frontend/components/investments/ConnectIBKRForm.tsx
"use client";
import { useState } from "react";
import { createBrokerConnection } from "@/lib/api/investments";
import { useRouter } from "next/navigation";

export function ConnectIBKRForm() {
  const router = useRouter();
  const [form, setForm] = useState({
    account_name: "Interactive Brokers",
    flex_token: "", query_id_positions: "", query_id_trades: "", base_currency: "EUR",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await createBrokerConnection({ provider: "ibkr_flex", ...form });
      router.push("/investments");
    } catch (e: any) { setErr(String(e.message ?? e)); }
    finally { setBusy(false); }
  }

  return (
    <form onSubmit={submit} className="space-y-3 max-w-md">
      {(["account_name", "flex_token", "query_id_positions", "query_id_trades", "base_currency"] as const).map(k => (
        <label key={k} className="block">
          <span className="text-sm">{k}</span>
          <input className="mt-1 w-full rounded border px-2 py-1"
                 value={(form as any)[k]} onChange={e => setForm({ ...form, [k]: e.target.value })} />
        </label>
      ))}
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button disabled={busy} className="rounded bg-primary text-primary-foreground px-3 py-2 text-sm">
        {busy ? "Connecting…" : "Connect IBKR"}
      </button>
      <p className="text-xs text-muted-foreground">
        Generate a Flex Token and two Flex Queries (positions + trades) in IBKR Account Management → Reports → Flex Queries → Flex Web Service.
      </p>
    </form>
  );
}
```

- [ ] **Step 2: `AddManualHoldingForm.tsx`**

```tsx
// frontend/components/investments/AddManualHoldingForm.tsx
"use client";
import { useState } from "react";
import { addManualHolding, createManualAccount, searchSymbols, SymbolSearchResult } from "@/lib/api/investments";
import { useRouter } from "next/navigation";

export function AddManualHoldingForm() {
  const router = useRouter();
  const [accountName, setAccountName] = useState("My Brokerage");
  const [baseCurrency, setBaseCurrency] = useState("EUR");
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [type, setType] = useState<"equity" | "etf" | "cash">("equity");
  const [currency, setCurrency] = useState("USD");
  const [asOf, setAsOf] = useState("");
  const [matches, setMatches] = useState<SymbolSearchResult[]>([]);
  const [err, setErr] = useState<string | null>(null);

  async function onSearch(q: string) {
    setSymbol(q);
    if (q.length >= 1) setMatches(await searchSymbols(q));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(null);
    try {
      const { account_id } = await createManualAccount(accountName, baseCurrency);
      await addManualHolding(account_id, {
        symbol, quantity, instrument_type: type, currency,
        ...(asOf ? { as_of_date: asOf } : {}),
      });
      router.push("/investments");
    } catch (e: any) { setErr(String(e.message ?? e)); }
  }

  return (
    <form onSubmit={submit} className="space-y-3 max-w-md">
      <label className="block"><span className="text-sm">Account name</span>
        <input className="mt-1 w-full rounded border px-2 py-1" value={accountName} onChange={e => setAccountName(e.target.value)} /></label>
      <label className="block"><span className="text-sm">Base currency</span>
        <input className="mt-1 w-full rounded border px-2 py-1" value={baseCurrency} onChange={e => setBaseCurrency(e.target.value)} /></label>
      <label className="block"><span className="text-sm">Symbol</span>
        <input className="mt-1 w-full rounded border px-2 py-1" value={symbol} onChange={e => onSearch(e.target.value)} list="symMatches" /></label>
      <datalist id="symMatches">
        {matches.map(m => <option key={m.symbol} value={m.symbol}>{m.name}</option>)}
      </datalist>
      <label className="block"><span className="text-sm">Quantity</span>
        <input className="mt-1 w-full rounded border px-2 py-1" value={quantity} onChange={e => setQuantity(e.target.value)} /></label>
      <label className="block"><span className="text-sm">Type</span>
        <select className="mt-1 w-full rounded border px-2 py-1" value={type} onChange={e => setType(e.target.value as any)}>
          <option value="equity">Equity</option><option value="etf">ETF</option><option value="cash">Cash</option>
        </select></label>
      <label className="block"><span className="text-sm">Currency</span>
        <input className="mt-1 w-full rounded border px-2 py-1" value={currency} onChange={e => setCurrency(e.target.value)} /></label>
      <label className="block"><span className="text-sm">Held since (optional)</span>
        <input type="date" className="mt-1 w-full rounded border px-2 py-1" value={asOf} onChange={e => setAsOf(e.target.value)} /></label>
      {err && <p className="text-sm text-red-600">{err}</p>}
      <button className="rounded bg-primary text-primary-foreground px-3 py-2 text-sm">Add holding</button>
    </form>
  );
}
```

- [ ] **Step 3: Page**

```tsx
// frontend/app/(dashboard)/investments/connect/page.tsx
import { ConnectIBKRForm } from "@/components/investments/ConnectIBKRForm";
import { AddManualHoldingForm } from "@/components/investments/AddManualHoldingForm";

export default function ConnectPage() {
  return (
    <div className="p-6 grid gap-8 md:grid-cols-2">
      <section>
        <h2 className="font-semibold mb-3">Connect Interactive Brokers</h2>
        <ConnectIBKRForm />
      </section>
      <section>
        <h2 className="font-semibold mb-3">Add a manual holding</h2>
        <AddManualHoldingForm />
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Type-check + commit**

```bash
cd frontend && pnpm tsc --noEmit && pnpm lint
git add frontend/app/\(dashboard\)/investments/connect/page.tsx frontend/components/investments/ConnectIBKRForm.tsx frontend/components/investments/AddManualHoldingForm.tsx
git commit -m "feat(investments): connect wizard for IBKR + manual flows"
```

---

### Task 19: Portfolio summary card on home dashboard

**Files:**
- Create: `frontend/components/investments/PortfolioSummaryCard.tsx`
- Modify: `frontend/app/(dashboard)/page.tsx` (or whichever file renders the home dashboard)

- [ ] **Step 1: Component**

```tsx
// frontend/components/investments/PortfolioSummaryCard.tsx
import Link from "next/link";
import { getPortfolio } from "@/lib/api/investments";

export async function PortfolioSummaryCard() {
  let portfolio;
  try { portfolio = await getPortfolio(); } catch { return null; }
  const total = Number(portfolio.total_value);
  if (!total) return null;
  const change = Number(portfolio.total_value_today_change);
  return (
    <Link href="/investments" className="block rounded-xl border p-4 hover:bg-muted/40">
      <div className="flex items-baseline justify-between">
        <h3 className="font-medium">Investments</h3>
        <span className={change >= 0 ? "text-green-600 text-sm" : "text-red-600 text-sm"}>
          {change >= 0 ? "+" : ""}{change.toFixed(2)} today
        </span>
      </div>
      <p className="text-2xl mt-1">{portfolio.total_value} {portfolio.currency}</p>
    </Link>
  );
}
```

- [ ] **Step 2: Mount on home dashboard**

Open the home dashboard page (likely `frontend/app/(dashboard)/page.tsx` — confirm with `ls frontend/app/\(dashboard\)/`). Append:

```tsx
import { PortfolioSummaryCard } from "@/components/investments/PortfolioSummaryCard";
// …inside the page JSX, at the bottom:
<section className="mt-6">
  <PortfolioSummaryCard />
</section>
```

- [ ] **Step 3: Type-check + commit**

```bash
cd frontend && pnpm tsc --noEmit && pnpm lint
git add frontend/components/investments/PortfolioSummaryCard.tsx frontend/app/\(dashboard\)/page.tsx
git commit -m "feat(investments): portfolio summary card on home dashboard"
```

---

### Task 20: Holdings tab on account detail page

**Files:**
- Modify: account detail page (find it: `grep -r 'accounts/\[' frontend/app | head -3`)

- [ ] **Step 1: Identify the account detail page** and conditionally render `<HoldingsTable holdings={...} />` when `account.account_type` is `investment_brokerage` or `investment_manual`. Fetch with `listHoldings(accountId)`.

- [ ] **Step 2: Type-check + commit**

```bash
cd frontend && pnpm tsc --noEmit && pnpm lint
git add -A frontend/app
git commit -m "feat(investments): holdings tab on investment account detail"
```

---

## Phase 9 — End-to-end smoke

### Task 21: Full backend test pass + manual smoke

- [ ] **Step 1: Run full backend test suite**

Run: `cd backend && pytest -q`
Expected: all tests pass (no regressions in existing suites).

- [ ] **Step 2: Boot backend + frontend and smoke-test the manual flow**

Terminal A: `cd backend && uvicorn app.main:app --reload`
Terminal B: `cd frontend && pnpm dev`

In the browser:
1. Navigate to `/investments/connect` → fill the manual holding form (e.g. `AAPL`, qty `1`, USD).
2. Wait for the redirect to `/investments` → verify the holding appears with a price + value.
3. Confirm the home dashboard shows the `PortfolioSummaryCard` with the portfolio value.

- [ ] **Step 3: Smoke-test IBKR flow** (only if you have a Flex token handy)

1. Navigate to `/investments/connect` → fill the IBKR form with a valid token + the two query IDs.
2. Re-load `/investments` after ~30s; positions, cash, and trades should populate.

- [ ] **Step 4: Final commit (if any nits surfaced)**

```bash
git add -A && git diff --cached --quiet || git commit -m "chore(investments): smoke-test fixes"
```

---

## Self-review checklist (verified)

- [x] Spec coverage: all sections (data model, modules, API, MCP tools, sync flow, security, env, migrations, testing) have corresponding tasks.
- [x] No placeholders ("TBD"/"TODO") in plan steps.
- [x] Type/method signatures consistent across tasks (`compute(account_id, on)`, `get_or_fetch(symbols, on)`, `sync_account(account_id, on)`).
- [x] Migration numbering (`0005_investments.sql`) follows existing convention.
- [x] Schema is added in Drizzle first, mirrored in SQLAlchemy — matches repo policy ("schema migrations are owned by Drizzle").
- [x] FX adapter contract is documented; if `ExchangeRateService` exposes a different method name, Task 11 explicitly says to adapt.
- [x] `User.base_currency` assumption flagged in Task 9 with instructions to add it if missing.
- [x] MCP tool registration adapts to whatever pattern `app/mcp/tools/accounts.py` uses (Task 14 instructs the engineer to inspect first).
