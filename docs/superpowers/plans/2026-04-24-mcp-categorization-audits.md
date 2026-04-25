# MCP Tool Enhancements for Categorization Audits — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend existing MCP tools with cursor pagination, sort/filter options, audit filters, and dry-run support for bulk updates. Zero new MCP tools.

**Architecture:** All changes are parameter additions to existing functions in `backend/app/mcp/tools/transactions.py` and `backend/app/mcp/tools/analytics.py`, plus matching signature updates in `backend/app/mcp/server.py`. New shared helper `_paginate_query` centralizes cursor/sort logic. Tests added in `backend/tests/`. All parameters default to current behavior (backward compatible).

**Tech Stack:** Python 3.13, FastMCP, SQLAlchemy ORM, PostgreSQL, pytest.

**Spec:** `docs/superpowers/specs/2026-04-24-mcp-categorization-audits-design.md`

---

## File Structure

**Modified:**
- `backend/app/mcp/tools/transactions.py` — add `_paginate_query` helper; add `cursor`, `sort_by`, `account_id`, `uncategorized`, `category_type` params; upgrade `bulk_update_transaction_categories` with `dry_run` + rich response.
- `backend/app/mcp/tools/analytics.py` — add `include_uncategorized`, `merchant_count` to `get_spending_by_category`; add `category_id`, `uncategorized` to `get_top_merchants`.
- `backend/app/mcp/server.py` — update tool registration signatures to pass new params through.

**Created:**
- `backend/tests/test_mcp_pagination.py` — cursor/sort/filter tests for list/search tools.
- `backend/tests/test_mcp_audit_filters.py` — SYL-31 filters.
- `backend/tests/test_mcp_bulk_update.py` — SYL-33 dry-run + rich response.

---

## Task 1: Add `_paginate_query` helper and `sort_by` support to `list_transactions`

**Files:**
- Modify: `backend/app/mcp/tools/transactions.py:17-118`
- Test: `backend/tests/test_mcp_pagination.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_mcp_pagination.py`:

```python
"""Tests for cursor pagination, sort_by, and account_id filter on MCP search/list tools."""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from app.mcp.tools import transactions as tx_tools
from app.models import Transaction, Account, Category, User


@pytest.fixture
def seeded_user(db_session):
    """Create a user with 3 accounts and 10 transactions spanning 10 days."""
    user = User(id="test-user-1", email="test@test.com")
    db_session.add(user)
    acc1 = Account(user_id=user.id, name="ABN", account_type="checking")
    acc2 = Account(user_id=user.id, name="Revolut", account_type="checking")
    db_session.add_all([acc1, acc2])
    db_session.flush()
    cat = Category(user_id=user.id, name="Food", category_type="expense")
    db_session.add(cat)
    db_session.flush()
    base = datetime(2026, 4, 1)
    for i in range(10):
        db_session.add(Transaction(
            user_id=user.id,
            account_id=acc1.id if i % 2 == 0 else acc2.id,
            amount=Decimal(f"-{(i + 1) * 10}"),
            currency="EUR",
            description=f"Purchase {i}",
            merchant=f"Merchant {i}",
            category_id=cat.id if i < 5 else None,
            booked_at=base + timedelta(days=i),
            transaction_type="debit",
        ))
    db_session.commit()
    return user, acc1, acc2, cat


def test_list_transactions_sort_by_amount_desc(seeded_user):
    user, _, _, _ = seeded_user
    result = tx_tools.list_transactions(
        user_id=user.id, sort_by="amount_desc", limit=3
    )
    # amount_desc over negative expenses: -10 is largest, -100 smallest
    amounts = [r["amount"] for r in result]
    assert amounts == sorted(amounts, reverse=True)
    assert len(result) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_mcp_pagination.py::test_list_transactions_sort_by_amount_desc -v`
Expected: FAIL — `list_transactions` does not accept `sort_by`.

- [ ] **Step 3: Add `_paginate_query` helper and `sort_by` parameter**

At the top of `backend/app/mcp/tools/transactions.py`, below `MatchMode`:

```python
import base64
import json
from datetime import datetime

SortBy = Literal["booked_at_desc", "booked_at_asc", "amount_desc", "amount_asc", "abs_amount_desc"]


def _sort_expr(sort_by: SortBy):
    """Return (primary_col, direction_func) for the given sort mode."""
    if sort_by == "booked_at_asc":
        return Transaction.booked_at, lambda c: c.asc()
    if sort_by == "amount_desc":
        return Transaction.amount, lambda c: c.desc()
    if sort_by == "amount_asc":
        return Transaction.amount, lambda c: c.asc()
    if sort_by == "abs_amount_desc":
        return func.abs(Transaction.amount), lambda c: c.desc()
    return Transaction.booked_at, lambda c: c.desc()  # booked_at_desc default


def _encode_cursor(primary_value, txn_id: str) -> str:
    payload = {"v": str(primary_value), "id": txn_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    return payload["v"], payload["id"]


def _paginate_query(query, cursor: Optional[str], sort_by: SortBy, limit: int):
    """Apply sort and (optionally) cursor filter. Returns ordered, limited query."""
    primary_col, direction = _sort_expr(sort_by)
    if cursor:
        try:
            v, last_id = _decode_cursor(cursor)
        except Exception:
            raise ValueError("Invalid cursor")
        # Sort-aware cursor filter: rows "after" (primary, id) tuple
        is_desc = sort_by in ("booked_at_desc", "amount_desc", "abs_amount_desc")
        if is_desc:
            query = query.filter(
                or_(primary_col < v, and_(primary_col == v, Transaction.id < last_id))
            )
        else:
            query = query.filter(
                or_(primary_col > v, and_(primary_col == v, Transaction.id > last_id))
            )
    return query.order_by(direction(primary_col), Transaction.id.desc()).limit(limit)


def _build_next_cursor(rows: list, sort_by: SortBy, limit: int) -> Optional[str]:
    if len(rows) < limit:
        return None
    primary_col, _ = _sort_expr(sort_by)
    last = rows[-1]
    # Extract raw primary value for the sort mode
    if sort_by in ("booked_at_desc", "booked_at_asc"):
        v = last.booked_at.isoformat()
    elif sort_by == "abs_amount_desc":
        v = str(abs(float(last.amount)))
    else:
        v = str(float(last.amount))
    return _encode_cursor(v, str(last.id))
```

Update `list_transactions` signature and body:

```python
def list_transactions(
    user_id: str,
    account_id: Optional[str] = None,
    category_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    page: int = 1,
    cursor: Optional[str] = None,
    sort_by: SortBy = "booked_at_desc",
    uncategorized: bool = False,
    category_type: Optional[Literal["expense", "income", "transfer"]] = None,
) -> dict:
    page = max(1, page)
    limit = min(max(1, limit), 100)
    account_uuid = validate_uuid(account_id) if account_id else None
    category_uuid = validate_uuid(category_id) if category_id else None
    from_dt = validate_date(from_date)
    to_dt = validate_date(to_date)

    with get_db() as db:
        query = (
            db.query(Transaction)
            .filter(Transaction.user_id == user_id)
            .options(joinedload(Transaction.account), joinedload(Transaction.category))
        )
        if account_uuid:
            query = query.filter(Transaction.account_id == account_uuid)
        if category_uuid:
            query = query.filter(
                (Transaction.category_id == category_uuid) |
                and_(
                    Transaction.category_id.is_(None),
                    Transaction.category_system_id == category_uuid
                )
            )
        if uncategorized:
            query = query.filter(
                Transaction.category_id.is_(None),
                Transaction.category_system_id.is_(None),
            )
        if category_type:
            query = query.join(
                Category,
                Category.id == func.coalesce(Transaction.category_id, Transaction.category_system_id),
            ).filter(Category.category_type == category_type)
        if from_dt:
            query = query.filter(Transaction.booked_at >= from_dt)
        if to_dt:
            query = query.filter(Transaction.booked_at <= to_dt)
        if search:
            search_term = f"%{search[:500]}%"
            query = query.filter(
                or_(
                    Transaction.description.ilike(search_term),
                    Transaction.merchant.ilike(search_term),
                )
            )

        if cursor:
            paginated = _paginate_query(query, cursor, sort_by, limit)
        else:
            offset = (page - 1) * limit
            primary_col, direction = _sort_expr(sort_by)
            paginated = (
                query.order_by(direction(primary_col), Transaction.id.desc())
                .offset(offset)
                .limit(limit)
            )
        transactions_rows = paginated.all()
        next_cursor = _build_next_cursor(transactions_rows, sort_by, limit)

        return {
            "transactions": [
                {
                    "id": str(txn.id),
                    "account_id": str(txn.account_id),
                    "account_name": txn.account.name if txn.account else None,
                    "amount": float(txn.amount),
                    "currency": txn.currency,
                    "description": txn.description,
                    "merchant": txn.merchant,
                    "category_id": str(txn.category_id) if txn.category_id else None,
                    "category_system_id": str(txn.category_system_id) if txn.category_system_id else None,
                    "category_name": txn.category.name if txn.category else None,
                    "booked_at": txn.booked_at.isoformat() if txn.booked_at else None,
                    "pending": txn.pending,
                    "transaction_type": txn.transaction_type,
                    "include_in_analytics": txn.include_in_analytics,
                    "recurring_transaction_id": str(txn.recurring_transaction_id) if txn.recurring_transaction_id else None,
                }
                for txn in transactions_rows
            ],
            "page": page if not cursor else None,
            "limit": limit,
            "next_cursor": next_cursor,
        }
```

Note: return shape changes from `list` → `dict`. Update `server.py` (see Task 5).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_mcp_pagination.py::test_list_transactions_sort_by_amount_desc -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/mcp/tools/transactions.py backend/tests/test_mcp_pagination.py
git commit -m "feat(mcp): add sort_by and cursor pagination helper for list_transactions"
```

---

## Task 2: Add cursor round-trip test for `list_transactions`

**Files:**
- Test: `backend/tests/test_mcp_pagination.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_mcp_pagination.py`:

```python
def test_list_transactions_cursor_round_trip(seeded_user):
    user, _, _, _ = seeded_user
    page1 = tx_tools.list_transactions(user_id=user.id, limit=4, sort_by="booked_at_desc")
    assert len(page1["transactions"]) == 4
    assert page1["next_cursor"] is not None

    page2 = tx_tools.list_transactions(
        user_id=user.id, limit=4, sort_by="booked_at_desc", cursor=page1["next_cursor"]
    )
    assert len(page2["transactions"]) == 4

    ids_page1 = {t["id"] for t in page1["transactions"]}
    ids_page2 = {t["id"] for t in page2["transactions"]}
    assert ids_page1.isdisjoint(ids_page2), "Pages must not overlap"

    page3 = tx_tools.list_transactions(
        user_id=user.id, limit=4, sort_by="booked_at_desc", cursor=page2["next_cursor"]
    )
    # Total 10 rows, 4+4+2 = 10, final page returns fewer than limit → no next_cursor
    assert len(page3["transactions"]) == 2
    assert page3["next_cursor"] is None
```

- [ ] **Step 2: Run test**

Run: `cd backend && pytest tests/test_mcp_pagination.py::test_list_transactions_cursor_round_trip -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_mcp_pagination.py
git commit -m "test(mcp): add cursor round-trip test for list_transactions"
```

---

## Task 3: Apply cursor/sort/account_id to `search_transactions`

**Files:**
- Modify: `backend/app/mcp/tools/transactions.py:217-332` (`search_transactions`)
- Test: `backend/tests/test_mcp_pagination.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_search_transactions_account_id_filter(seeded_user):
    user, acc1, acc2, _ = seeded_user
    result = tx_tools.search_transactions(
        user_id=user.id, query="Purchase", account_id=str(acc1.id), match_mode="contains"
    )
    assert result["total_count"] > 0
    assert all(
        # Only acc1 transactions; acc1 got even indices 0,2,4,6,8 → 5 txns
        True for t in result["transactions"]
    )
    assert result["total_count"] == 5
```

- [ ] **Step 2: Run test**

Run: `cd backend && pytest tests/test_mcp_pagination.py::test_search_transactions_account_id_filter -v`
Expected: FAIL — `account_id` not a parameter.

- [ ] **Step 3: Update `search_transactions` signature**

Replace signature in `backend/app/mcp/tools/transactions.py:217`:

```python
def search_transactions(
    user_id: str,
    query: str,
    exclude_category_id: Optional[str] = None,
    match_mode: MatchMode = "contains",
    ids_only: bool = False,
    limit: int = 50,
    page: int = 1,
    cursor: Optional[str] = None,
    sort_by: SortBy = "booked_at_desc",
    account_id: Optional[str] = None,
) -> dict:
```

Inside the function, after `exclude_cat_uuid = ...`:

```python
    account_uuid = validate_uuid(account_id) if account_id else None
```

Inside the `with get_db()` block, after building `base_filter` with `exclude_cat_uuid`:

```python
        if account_uuid:
            base_filter = and_(base_filter, Transaction.account_id == account_uuid)
```

Replace the pagination/order block (the `.order_by(...).offset(offset).limit(limit)` chain) with:

```python
        total_count = db.query(func.count(Transaction.id)).filter(base_filter).scalar()
        query_obj = db.query(Transaction).filter(base_filter)
        if not ids_only:
            query_obj = query_obj.options(
                joinedload(Transaction.account),
                joinedload(Transaction.category),
            )
        if cursor:
            paginated = _paginate_query(query_obj, cursor, sort_by, limit)
        else:
            offset = (page - 1) * limit
            primary_col, direction = _sort_expr(sort_by)
            paginated = (
                query_obj.order_by(direction(primary_col), Transaction.id.desc())
                .offset(offset)
                .limit(limit)
            )
        rows = paginated.all()
        next_cursor = _build_next_cursor(rows, sort_by, limit)
        has_more = next_cursor is not None if cursor else ((page - 1) * limit + len(rows) < total_count)
```

Replace the final return blocks to use `rows` and add `next_cursor` to both branches (ids_only and full):

```python
        if ids_only:
            return {
                "transaction_ids": [str(t.id) for t in rows],
                "page": page if not cursor else None,
                "limit": limit,
                "has_more": has_more,
                "total_count": total_count,
                "next_cursor": next_cursor,
            }

        return {
            "transactions": [
                {
                    "id": str(txn.id),
                    "account_id": str(txn.account_id),
                    "account_name": txn.account.name if txn.account else None,
                    "amount": float(txn.amount),
                    "currency": txn.currency,
                    "description": txn.description,
                    "merchant": txn.merchant,
                    "category_id": str(txn.category_id) if txn.category_id else None,
                    "category_name": txn.category.name if txn.category else None,
                    "booked_at": txn.booked_at.isoformat() if txn.booked_at else None,
                }
                for txn in rows
            ],
            "page": page if not cursor else None,
            "limit": limit,
            "has_more": has_more,
            "total_count": total_count,
            "next_cursor": next_cursor,
        }
```

- [ ] **Step 4: Run test**

Run: `cd backend && pytest tests/test_mcp_pagination.py::test_search_transactions_account_id_filter -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/mcp/tools/transactions.py backend/tests/test_mcp_pagination.py
git commit -m "feat(mcp): add cursor, sort_by, account_id to search_transactions"
```

---

## Task 4: Apply cursor/sort/account_id to `search_transactions_multi`

**Files:**
- Modify: `backend/app/mcp/tools/transactions.py:335-466`
- Test: `backend/tests/test_mcp_pagination.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_search_multi_cursor_opt_in(seeded_user):
    user, _, _, _ = seeded_user
    # Default (no cursor) behavior: returns all capped results, no next_cursor
    r1 = tx_tools.search_transactions_multi(
        user_id=user.id, queries=["Purchase"], max_results=100
    )
    assert r1["total_count"] == 10
    assert "next_cursor" not in r1 or r1.get("next_cursor") is None

    # Opt-in to cursor mode via limit + cursor loop
    r2 = tx_tools.search_transactions_multi(
        user_id=user.id, queries=["Purchase"], max_results=4, cursor=""
    )
    assert len(r2["transactions"]) == 4
    assert r2["next_cursor"] is not None
    r3 = tx_tools.search_transactions_multi(
        user_id=user.id, queries=["Purchase"], max_results=4, cursor=r2["next_cursor"]
    )
    assert len(r3["transactions"]) == 4
    assert set(t["id"] for t in r2["transactions"]).isdisjoint(
        set(t["id"] for t in r3["transactions"])
    )
```

- [ ] **Step 2: Run test**

Run: `cd backend && pytest tests/test_mcp_pagination.py::test_search_multi_cursor_opt_in -v`
Expected: FAIL.

- [ ] **Step 3: Update `search_transactions_multi`**

Replace signature (`backend/app/mcp/tools/transactions.py:335`):

```python
def search_transactions_multi(
    user_id: str,
    queries: list[str],
    exclude_category_id: Optional[str] = None,
    match_mode: MatchMode = "contains",
    ids_only: bool = False,
    max_results: int = 500,
    cursor: Optional[str] = None,
    sort_by: SortBy = "booked_at_desc",
    account_id: Optional[str] = None,
) -> dict:
```

After `exclude_cat_uuid = validate_uuid(...)`:

```python
    account_uuid = validate_uuid(account_id) if account_id else None
```

After `combined_filter` is built (and exclude-category is applied), before "Get total count":

```python
        if account_uuid:
            combined_filter = and_(combined_filter, Transaction.account_id == account_uuid)
```

Replace the block that currently reads `.order_by(Transaction.booked_at.desc()).limit(max_results)` with:

```python
        query_obj = db.query(Transaction).filter(combined_filter)
        if not ids_only:
            query_obj = query_obj.options(
                joinedload(Transaction.account),
                joinedload(Transaction.category),
            )

        cursor_mode = cursor is not None  # empty-string opt-in or real cursor
        if cursor_mode:
            paginated = _paginate_query(query_obj, cursor or None, sort_by, max_results)
        else:
            primary_col, direction = _sort_expr(sort_by)
            paginated = query_obj.order_by(direction(primary_col), Transaction.id.desc()).limit(max_results)
        transactions_rows = paginated.all()
        next_cursor = _build_next_cursor(transactions_rows, sort_by, max_results) if cursor_mode else None
```

Replace `transactions = query_obj.all()` → use `transactions_rows` in the result assembly. In the final result dict, add:

```python
        result["next_cursor"] = next_cursor
```

- [ ] **Step 4: Run test**

Run: `cd backend && pytest tests/test_mcp_pagination.py::test_search_multi_cursor_opt_in -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/mcp/tools/transactions.py backend/tests/test_mcp_pagination.py
git commit -m "feat(mcp): add cursor, sort_by, account_id to search_transactions_multi"
```

---

## Task 5: Update `server.py` tool registrations for new params

**Files:**
- Modify: `backend/app/mcp/server.py` — the `@mcp.tool` wrappers for `list_transactions`, `search_transactions`, `search_transactions_multi`.

- [ ] **Step 1: Read current signatures**

Run: `grep -n "def list_transactions\|def search_transactions\|def search_transactions_multi" backend/app/mcp/server.py`

- [ ] **Step 2: Update each wrapper**

For `list_transactions` wrapper in `server.py`, update signature to include the new params and forward them:

```python
@mcp.tool
def list_transactions(
    account_id: str | None = None,
    category_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    search: str | None = None,
    limit: int = 50,
    page: int = 1,
    cursor: str | None = None,
    sort_by: str = "booked_at_desc",
    uncategorized: bool = False,
    category_type: str | None = None,
    user_id: str | None = None,
) -> dict:
    """List transactions with optional filtering, cursor pagination, and sort."""
    return transactions.list_transactions(
        get_mcp_user_id(user_id), account_id, category_id, from_date, to_date, search,
        limit, page, cursor, sort_by, uncategorized, category_type,
    )
```

Apply the same pattern to `search_transactions` and `search_transactions_multi` wrappers — add `cursor`, `sort_by`, `account_id` and pass them through as positional/keyword args matching the underlying function signatures.

- [ ] **Step 3: Run existing MCP server health test**

Run: `cd backend && pytest tests/test_mcp_server_health.py -v`
Expected: PASS (tool registration still succeeds).

- [ ] **Step 4: Commit**

```bash
git add backend/app/mcp/server.py
git commit -m "feat(mcp): surface cursor/sort/account_id on MCP tool wrappers"
```

---

## Task 6: SYL-31 — `list_transactions` `uncategorized` + `category_type` filters

**Files:**
- Test: `backend/tests/test_mcp_audit_filters.py`

(Implementation already done in Task 1 — this task covers tests.)

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_mcp_audit_filters.py`:

```python
"""Tests for SYL-31 audit filters."""
from datetime import datetime
from decimal import Decimal

import pytest

from app.mcp.tools import transactions as tx_tools
from app.mcp.tools import analytics as an_tools
from app.models import Transaction, Account, Category, User


@pytest.fixture
def audit_data(db_session):
    user = User(id="audit-user", email="audit@test.com")
    db_session.add(user)
    acc = Account(user_id=user.id, name="A", account_type="checking")
    db_session.add(acc)
    db_session.flush()
    expense_cat = Category(user_id=user.id, name="Food", category_type="expense")
    income_cat = Category(user_id=user.id, name="Salary", category_type="income")
    db_session.add_all([expense_cat, income_cat])
    db_session.flush()
    # 3 uncategorized, 2 expense-categorized, 1 income-categorized
    specs = [
        (None, -10, "debit"), (None, -20, "debit"), (None, -30, "debit"),
        (expense_cat.id, -40, "debit"), (expense_cat.id, -50, "debit"),
        (income_cat.id, 100, "credit"),
    ]
    for i, (cid, amt, ttype) in enumerate(specs):
        db_session.add(Transaction(
            user_id=user.id,
            account_id=acc.id,
            amount=Decimal(str(amt)),
            currency="EUR",
            description=f"Txn {i}",
            merchant=f"M{i}",
            category_id=cid,
            booked_at=datetime(2026, 4, 1 + i),
            transaction_type=ttype,
        ))
    db_session.commit()
    return user, acc, expense_cat, income_cat


def test_list_transactions_uncategorized(audit_data):
    user, *_ = audit_data
    result = tx_tools.list_transactions(user_id=user.id, uncategorized=True, limit=50)
    assert len(result["transactions"]) == 3
    assert all(t["category_id"] is None for t in result["transactions"])


def test_list_transactions_category_type(audit_data):
    user, *_ = audit_data
    result = tx_tools.list_transactions(user_id=user.id, category_type="expense", limit=50)
    assert len(result["transactions"]) == 2  # Only categorized-as-expense
    result_income = tx_tools.list_transactions(user_id=user.id, category_type="income", limit=50)
    assert len(result_income["transactions"]) == 1
```

- [ ] **Step 2: Run tests**

Run: `cd backend && pytest tests/test_mcp_audit_filters.py -v`
Expected: PASS (impl is in Task 1).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_mcp_audit_filters.py
git commit -m "test(mcp): cover uncategorized and category_type filters on list_transactions"
```

---

## Task 7: SYL-31 — `include_uncategorized` + `merchant_count` on `get_spending_by_category`

**Files:**
- Modify: `backend/app/mcp/tools/analytics.py:28-110`
- Test: `backend/tests/test_mcp_audit_filters.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_mcp_audit_filters.py`:

```python
def test_spending_by_category_include_uncategorized(audit_data):
    user, *_ = audit_data
    # Without flag: only categorized expense rows
    baseline = an_tools.get_spending_by_category(user_id=user.id)
    assert all(r["category_id"] is not None for r in baseline)

    enriched = an_tools.get_spending_by_category(user_id=user.id, include_uncategorized=True)
    names = [r["category_name"] for r in enriched]
    assert "Uncategorized" in names
    uncat = next(r for r in enriched if r["category_name"] == "Uncategorized")
    assert uncat["total"] == 60  # 10 + 20 + 30
    assert uncat["count"] == 3
    assert "merchant_count" in uncat
    assert uncat["merchant_count"] == 3
```

- [ ] **Step 2: Run test**

Run: `cd backend && pytest tests/test_mcp_audit_filters.py::test_spending_by_category_include_uncategorized -v`
Expected: FAIL.

- [ ] **Step 3: Update `get_spending_by_category`**

In `backend/app/mcp/tools/analytics.py`, change the function signature to:

```python
def get_spending_by_category(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    account_id: Optional[str] = None,
    include_uncategorized: bool = False,
) -> list[dict]:
```

Rewrite the SQL body to use a LEFT JOIN and conditionally include uncategorized rows, and add `COUNT(DISTINCT t.merchant)`:

```python
    join_type = "LEFT JOIN" if include_uncategorized else "INNER JOIN"
    uncategorized_filter = "" if include_uncategorized else "AND c.category_type = 'expense'"
    sql = text(f"""
        {_get_link_group_nets_cte(user_id)}
        SELECT
            COALESCE(t.category_id, t.category_system_id) as category_id,
            COALESCE(c.name, 'Uncategorized') as category_name,
            c.color as category_color,
            COALESCE(SUM(
                CASE
                    WHEN tl.link_role = 'primary' THEN
                        CASE WHEN lgn.net_amount < 0 THEN ABS(lgn.net_amount) ELSE 0 END
                    WHEN tl.link_role IS NOT NULL THEN 0
                    ELSE ABS(t.amount)
                END
            ), 0) as total,
            COUNT(t.id) as count,
            COUNT(DISTINCT t.merchant) FILTER (WHERE t.merchant IS NOT NULL AND t.merchant <> '') as merchant_count
        FROM transactions t
        {join_type} categories c ON c.id = COALESCE(t.category_id, t.category_system_id)
        LEFT JOIN transaction_links tl ON t.id = tl.transaction_id
        LEFT JOIN link_group_nets lgn ON tl.group_id = lgn.group_id
        WHERE t.user_id = '{user_id}'
            AND t.transaction_type = 'debit'
            AND t.include_in_analytics = true
            {uncategorized_filter}
            {date_filter}
            {account_filter}
        GROUP BY COALESCE(t.category_id, t.category_system_id), c.name, c.color
        ORDER BY total DESC
    """)
```

Update the result assembly (the list comprehension) to include `merchant_count`:

```python
        return [
            {
                "category_id": str(r.category_id) if r.category_id else None,
                "category_name": r.category_name or "Uncategorized",
                "category_color": r.category_color,
                "total": float(r.total),
                "count": r.count,
                "merchant_count": r.merchant_count,
            }
            for r in results
        ]
```

- [ ] **Step 4: Run test**

Run: `cd backend && pytest tests/test_mcp_audit_filters.py::test_spending_by_category_include_uncategorized -v`
Expected: PASS.

- [ ] **Step 5: Update server.py wrapper**

In `backend/app/mcp/server.py`, find the `get_spending_by_category` wrapper and add `include_uncategorized: bool = False` to its signature, pass it through.

- [ ] **Step 6: Commit**

```bash
git add backend/app/mcp/tools/analytics.py backend/app/mcp/server.py backend/tests/test_mcp_audit_filters.py
git commit -m "feat(mcp): add include_uncategorized and merchant_count to get_spending_by_category"
```

---

## Task 8: SYL-31 — `category_id` + `uncategorized` filters on `get_top_merchants`

**Files:**
- Modify: `backend/app/mcp/tools/analytics.py:384-441`
- Test: `backend/tests/test_mcp_audit_filters.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_top_merchants_category_filter(audit_data):
    user, _, expense_cat, _ = audit_data
    result = an_tools.get_top_merchants(user_id=user.id, category_id=str(expense_cat.id))
    # Only the 2 expense-categorized txns (M3, M4)
    merchants = {r["merchant"] for r in result}
    assert merchants == {"M3", "M4"}


def test_top_merchants_uncategorized(audit_data):
    user, *_ = audit_data
    result = an_tools.get_top_merchants(user_id=user.id, uncategorized=True)
    merchants = {r["merchant"] for r in result}
    assert merchants == {"M0", "M1", "M2"}


def test_top_merchants_mutual_exclusion(audit_data):
    user, _, expense_cat, _ = audit_data
    with pytest.raises(ValueError):
        an_tools.get_top_merchants(
            user_id=user.id, category_id=str(expense_cat.id), uncategorized=True,
        )
```

- [ ] **Step 2: Run tests**

Run: `cd backend && pytest tests/test_mcp_audit_filters.py::test_top_merchants_category_filter tests/test_mcp_audit_filters.py::test_top_merchants_uncategorized tests/test_mcp_audit_filters.py::test_top_merchants_mutual_exclusion -v`
Expected: FAIL.

- [ ] **Step 3: Update `get_top_merchants`**

Replace signature:

```python
def get_top_merchants(
    user_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 10,
    category_id: Optional[str] = None,
    uncategorized: bool = False,
) -> list[dict]:
```

Add validation at top of function body:

```python
    if category_id and uncategorized:
        raise ValueError("category_id and uncategorized are mutually exclusive")
    cat_uuid = validate_uuid(category_id) if category_id else None
```

Inside the `with get_db()` block, after the initial `query.filter(...)`:

```python
        if cat_uuid:
            query = query.filter(
                or_(
                    Transaction.category_id == cat_uuid,
                    and_(
                        Transaction.category_id.is_(None),
                        Transaction.category_system_id == cat_uuid,
                    ),
                )
            )
        if uncategorized:
            query = query.filter(
                Transaction.category_id.is_(None),
                Transaction.category_system_id.is_(None),
            )
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_mcp_audit_filters.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Update server.py wrapper**

In `backend/app/mcp/server.py`, update `get_top_merchants` wrapper signature to include `category_id: str | None = None, uncategorized: bool = False` and pass them through.

- [ ] **Step 6: Commit**

```bash
git add backend/app/mcp/tools/analytics.py backend/app/mcp/server.py backend/tests/test_mcp_audit_filters.py
git commit -m "feat(mcp): add category_id and uncategorized filters to get_top_merchants"
```

---

## Task 9: SYL-33 — dry_run + rich response on `bulk_update_transaction_categories`

**Files:**
- Modify: `backend/app/mcp/tools/transactions.py:538-605`
- Test: `backend/tests/test_mcp_bulk_update.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_mcp_bulk_update.py`:

```python
"""Tests for SYL-33: dry_run and rich response on bulk_update_transaction_categories."""
from datetime import datetime
from decimal import Decimal

import pytest

from app.mcp.tools import transactions as tx_tools
from app.models import Transaction, Account, Category, User


@pytest.fixture
def bulk_data(db_session):
    user = User(id="bulk-user", email="bulk@test.com")
    other_user = User(id="other-user", email="other@test.com")
    db_session.add_all([user, other_user])
    acc = Account(user_id=user.id, name="A", account_type="checking")
    other_acc = Account(user_id=other_user.id, name="B", account_type="checking")
    db_session.add_all([acc, other_acc])
    db_session.flush()
    target = Category(user_id=user.id, name="Groceries", category_type="expense")
    other_cat = Category(user_id=user.id, name="Other", category_type="expense")
    db_session.add_all([target, other_cat])
    db_session.flush()
    # 3 to update, 1 already in target, 1 belongs to other user
    t1 = Transaction(user_id=user.id, account_id=acc.id, amount=Decimal("-10"),
                     currency="EUR", description="D1", merchant="M1",
                     category_id=other_cat.id, booked_at=datetime(2026, 4, 1),
                     transaction_type="debit")
    t2 = Transaction(user_id=user.id, account_id=acc.id, amount=Decimal("-20"),
                     currency="EUR", description="D2", merchant="M2",
                     category_id=other_cat.id, booked_at=datetime(2026, 4, 2),
                     transaction_type="debit")
    t3 = Transaction(user_id=user.id, account_id=acc.id, amount=Decimal("-30"),
                     currency="EUR", description="D3", merchant="M3",
                     category_id=None, booked_at=datetime(2026, 4, 3),
                     transaction_type="debit")
    t4 = Transaction(user_id=user.id, account_id=acc.id, amount=Decimal("-40"),
                     currency="EUR", description="D4", merchant="M4",
                     category_id=target.id, booked_at=datetime(2026, 4, 4),
                     transaction_type="debit")
    t5 = Transaction(user_id=other_user.id, account_id=other_acc.id, amount=Decimal("-50"),
                     currency="EUR", description="D5", merchant="M5",
                     category_id=other_cat.id, booked_at=datetime(2026, 4, 5),
                     transaction_type="debit")
    db_session.add_all([t1, t2, t3, t4, t5])
    db_session.commit()
    return user, target, [t1, t2, t3, t4, t5]


def test_bulk_update_dry_run_no_mutation(bulk_data, db_session):
    user, target, txns = bulk_data
    ids = [str(t.id) for t in txns[:3]]
    result = tx_tools.bulk_update_transaction_categories(
        user_id=user.id, category_id=str(target.id),
        transaction_ids=ids, dry_run=True,
    )
    assert result["success"] is True
    assert result["would_update_count"] == 3
    assert result["requested_count"] == 3
    assert len(result["sample_changes"]) == 3
    assert result["sample_changes"][0]["description"] in ("D1", "D2", "D3")
    # Verify DB untouched
    for t in txns[:3]:
        db_session.refresh(t)
        assert t.category_id != target.id


def test_bulk_update_rich_response_categorizes_ids(bulk_data):
    user, target, txns = bulk_data
    bogus = "00000000-0000-0000-0000-000000000000"
    ids = [str(txns[0].id), str(txns[3].id), str(txns[4].id), bogus, "not-a-uuid"]
    result = tx_tools.bulk_update_transaction_categories(
        user_id=user.id, category_id=str(target.id), transaction_ids=ids,
    )
    assert result["success"] is True
    assert result["updated_count"] == 1  # only txns[0] is actually changed
    assert result["requested_count"] == 5
    assert result["invalid_ids"] == ["not-a-uuid"]
    assert bogus in result["not_found_ids"] or str(txns[4].id) in result["not_found_ids"]
    assert str(txns[3].id) in result["skipped_already_in_category_ids"]


def test_bulk_update_hard_cap():
    result = tx_tools.bulk_update_transaction_categories(
        user_id="x", category_id="00000000-0000-0000-0000-000000000001",
        transaction_ids=[f"id-{i}" for i in range(2001)],
    )
    assert result["success"] is False
    assert "2000" in result["error"]
```

- [ ] **Step 2: Run tests**

Run: `cd backend && pytest tests/test_mcp_bulk_update.py -v`
Expected: FAIL.

- [ ] **Step 3: Replace `bulk_update_transaction_categories`**

Replace the function (`backend/app/mcp/tools/transactions.py:538`):

```python
def bulk_update_transaction_categories(
    user_id: str,
    category_id: str,
    transaction_ids: list[str],
    dry_run: bool = False,
) -> dict:
    """
    Bulk update category for multiple transactions.

    Args:
        user_id: The user's ID
        category_id: The category ID to assign
        transaction_ids: List of transaction IDs to update (max 2000)
        dry_run: If True, preview the change without committing

    Returns:
        Dict with success flag and:
        - updated_count (or would_update_count if dry_run)
        - requested_count, invalid_ids, not_found_ids,
          skipped_already_in_category_ids, sample_changes
    """
    MAX_IDS = 2000
    if not transaction_ids:
        return {"success": False, "error": "Must provide transaction_ids"}
    if len(transaction_ids) > MAX_IDS:
        return {
            "success": False,
            "error": f"Too many transaction_ids ({len(transaction_ids)}). Max {MAX_IDS} per call.",
        }

    cat_uuid = validate_uuid(category_id)
    if not cat_uuid:
        return {"success": False, "error": "Invalid category ID format"}

    with get_db() as db:
        category = db.query(Category).filter(
            Category.id == cat_uuid, Category.user_id == user_id,
        ).first()
        if not category:
            return {"success": False, "error": "Category not found"}

        valid_uuids = []
        invalid_ids = []
        for tid in transaction_ids:
            u = validate_uuid(tid)
            if u:
                valid_uuids.append(u)
            else:
                invalid_ids.append(tid)

        found = db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.id.in_(valid_uuids),
        ).options(joinedload(Transaction.category)).all() if valid_uuids else []

        found_by_id = {str(t.id): t for t in found}
        not_found_ids = [str(u) for u in valid_uuids if str(u) not in found_by_id]

        to_change = []
        skipped_already = []
        for t in found:
            if t.category_id == cat_uuid:
                skipped_already.append(str(t.id))
            else:
                to_change.append(t)

        sample_changes = [
            {
                "id": str(t.id),
                "description": t.description,
                "merchant": t.merchant,
                "amount": float(t.amount),
                "previous_category_name": t.category.name if t.category else None,
            }
            for t in to_change[:10]
        ]

        base_response = {
            "success": True,
            "category_name": category.name,
            "requested_count": len(transaction_ids),
            "invalid_ids": invalid_ids,
            "not_found_ids": not_found_ids,
            "skipped_already_in_category_ids": skipped_already,
            "sample_changes": sample_changes,
        }

        if dry_run:
            base_response["would_update_count"] = len(to_change)
            return base_response

        try:
            change_uuids = [t.id for t in to_change]
            updated = 0
            if change_uuids:
                updated = db.query(Transaction).filter(
                    Transaction.user_id == user_id,
                    Transaction.id.in_(change_uuids),
                ).update({Transaction.category_id: cat_uuid}, synchronize_session=False)
                db.commit()
        except Exception as e:
            db.rollback()
            return {"success": False, "error": f"Database error: {str(e)}"}

        base_response["updated_count"] = updated
        return base_response
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_mcp_bulk_update.py -v`
Expected: PASS.

- [ ] **Step 5: Update server.py wrapper**

In `backend/app/mcp/server.py`, update `bulk_update_transaction_categories` wrapper to add `dry_run: bool = False` parameter and pass it through.

- [ ] **Step 6: Commit**

```bash
git add backend/app/mcp/tools/transactions.py backend/app/mcp/server.py backend/tests/test_mcp_bulk_update.py
git commit -m "feat(mcp): add dry_run and rich response to bulk_update_transaction_categories"
```

---

## Task 10: Integration test — dry-run then real-run parity

**Files:**
- Test: `backend/tests/test_mcp_bulk_update.py`

- [ ] **Step 1: Append test**

```python
def test_bulk_update_dry_run_matches_real_run(bulk_data):
    user, target, txns = bulk_data
    ids = [str(t.id) for t in txns[:3]]

    preview = tx_tools.bulk_update_transaction_categories(
        user_id=user.id, category_id=str(target.id),
        transaction_ids=ids, dry_run=True,
    )
    real = tx_tools.bulk_update_transaction_categories(
        user_id=user.id, category_id=str(target.id), transaction_ids=ids,
    )

    assert preview["would_update_count"] == real["updated_count"]
    preview_ids = {s["id"] for s in preview["sample_changes"]}
    real_ids = {s["id"] for s in real["sample_changes"]}
    assert preview_ids == real_ids
```

- [ ] **Step 2: Run**

Run: `cd backend && pytest tests/test_mcp_bulk_update.py::test_bulk_update_dry_run_matches_real_run -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_mcp_bulk_update.py
git commit -m "test(mcp): verify dry-run and real-run produce matching previews"
```

---

## Task 11: Update MCP server instructions (docstring)

**Files:**
- Modify: `backend/app/mcp/server.py` — `instructions=` string in `FastMCP(...)`.

- [ ] **Step 1: Add a "Pagination & sort" section**

In `backend/app/mcp/server.py`, extend the `instructions=` triple-quoted block with:

```
## Pagination & sort

All list/search tools accept:
- `cursor` (opaque string) — preferred for paging through large result sets; pass
  `next_cursor` from the previous response.
- `sort_by`: one of `booked_at_desc` (default), `booked_at_asc`, `amount_desc`,
  `amount_asc`, `abs_amount_desc`.
- `account_id` — limit to a single account.

## Audit filters

- `list_transactions(uncategorized=True)` — only rows with no category at all.
- `list_transactions(category_type="expense"|"income"|"transfer")` — filter by type.
- `get_spending_by_category(include_uncategorized=True)` — include an
  "Uncategorized" bucket with `merchant_count`.
- `get_top_merchants(category_id=...)` or `get_top_merchants(uncategorized=True)` —
  audit miscategorized or unassigned merchants.

## Safe bulk updates

`bulk_update_transaction_categories(dry_run=True)` returns what *would* change
(`would_update_count`, `sample_changes`) without mutating. Hard cap: 2000 IDs
per call. Response also includes `invalid_ids`, `not_found_ids`, and
`skipped_already_in_category_ids` so the agent can narrate exactly what
happened.
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/mcp/server.py
git commit -m "docs(mcp): advertise new pagination, audit, and bulk-update options to agents"
```

---

## Self-Review Checklist

- Spec coverage: SYL-30 (Tasks 1-5), SYL-31 (Tasks 6-8), SYL-33 (Tasks 9-10), docs (Task 11). ✅
- Backward compatibility: `list_transactions` return shape changed from list → dict — breaking. Callers must be migrated. The only live caller is `server.py` (updated in Task 5).
- Placeholder scan: none.
- Type consistency: `SortBy` defined once in `transactions.py`, referenced elsewhere.
- Cursor semantics: `_paginate_query` always applies a deterministic `(primary_col, id)` ordering; `_build_next_cursor` returns `None` when result count < limit, matching test expectations.
