# AI Categorizer Prompt Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the LLM categorizer's prompt with category descriptions and the user's account graph so it makes better first-pass decisions (SYL-32 prompt piece + SYL-29).

**Architecture:** All changes are inside `backend/app/services/category_matcher.py`'s LLM-prompt assembly functions. Add one `Account.alias_patterns` JSONB column with a raw-SQL migration script in `backend/postgres_migration/`. Feature flag behind `CATEGORIZER_ENRICHED_PROMPT`.

**Tech Stack:** Python 3.13, SQLAlchemy ORM, PostgreSQL (JSONB), OpenAI SDK, pytest.

**Spec:** `docs/superpowers/specs/2026-04-24-ai-categorizer-prompt-enrichment-design.md`

---

## File Structure

**Modified:**
- `backend/app/models.py` — add `alias_patterns` column to `Account`.
- `backend/app/services/category_matcher.py` — category-description rendering, `_build_account_context`, prompt assembly, budget cap.
- `backend/app/schemas.py` — expose `alias_patterns` on Pydantic account schemas.
- `backend/app/routes/*` — allow updating `alias_patterns` on the existing account-update endpoint (one line per route).

**Created:**
- `backend/postgres_migration/add_account_alias_patterns.py` — one-off migration runner.
- `backend/tests/test_category_matcher_prompt.py` — prompt-composition unit tests.
- `backend/tests/test_category_matcher_llm_transfer.py` — stub-OpenAI integration test.

---

## Task 1: Add `alias_patterns` column to `Account` model

**Files:**
- Modify: `backend/app/models.py:28-56`

- [ ] **Step 1: Update the model**

In `backend/app/models.py`, inside `class Account(Base):`, after the `is_active` column:

```python
    alias_patterns = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
```

Ensure the imports at the top include:

```python
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import text
```

(Both are likely already imported — verify with `grep -n "JSONB\|from sqlalchemy import" backend/app/models.py`.)

- [ ] **Step 2: Run existing account tests to verify model still loads**

Run: `cd backend && pytest tests/test_account_sync_encryption.py -v --no-header -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models.py
git commit -m "feat(models): add alias_patterns JSONB column to Account"
```

---

## Task 2: Write migration script for `alias_patterns` column

**Files:**
- Create: `backend/postgres_migration/add_account_alias_patterns.py`

- [ ] **Step 1: Create the migration script**

```python
"""
One-off migration: add accounts.alias_patterns JSONB column.

Usage (from backend/):
    python postgres_migration/add_account_alias_patterns.py

Idempotent: safe to re-run.
"""
import sys
from sqlalchemy import create_engine, text

from app.database import get_database_url


SQL = """
ALTER TABLE accounts
  ADD COLUMN IF NOT EXISTS alias_patterns JSONB NOT NULL DEFAULT '[]'::jsonb;
"""


def main() -> int:
    engine = create_engine(get_database_url())
    with engine.begin() as conn:
        conn.execute(text(SQL))
    print("OK: accounts.alias_patterns present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

If `get_database_url` doesn't exist, check `backend/app/database.py` for the engine/URL export and adapt the import line accordingly.

- [ ] **Step 2: Smoke-run against a local DB**

Run: `cd backend && python postgres_migration/add_account_alias_patterns.py`
Expected: `OK: accounts.alias_patterns present.`

- [ ] **Step 3: Re-run to confirm idempotency**

Run the same command again. Expected: same output, no error.

- [ ] **Step 4: Commit**

```bash
git add backend/postgres_migration/add_account_alias_patterns.py
git commit -m "feat(migration): add idempotent migration for Account.alias_patterns"
```

---

## Task 3: Expose `alias_patterns` on account Pydantic schemas

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Locate account schemas**

Run: `grep -n "class Account" backend/app/schemas.py`

- [ ] **Step 2: Add field to read/update schemas**

For every account-shaped schema (typically `AccountRead`, `AccountUpdate`, `AccountBase`), add:

```python
    alias_patterns: list[str] = Field(default_factory=list)
```

Import `Field` at the top if not already:

```python
from pydantic import BaseModel, Field
```

- [ ] **Step 3: Find the account update route and confirm it accepts `alias_patterns`**

Run: `grep -rn "AccountUpdate\|alias_patterns" backend/app/routes/`

If there's a manual field-copy in the update handler, add `alias_patterns` to it. If it uses `.model_dump(exclude_unset=True)` and applies via `setattr`, no route changes needed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas.py backend/app/routes
git commit -m "feat(schemas): expose alias_patterns on account read/update schemas"
```

---

## Task 4: Helper `_render_category_list` with descriptions (SYL-32)

**Files:**
- Modify: `backend/app/services/category_matcher.py`
- Test: `backend/tests/test_category_matcher_prompt.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_category_matcher_prompt.py`:

```python
"""Tests for SYL-32 / SYL-29 prompt enrichment."""
from unittest.mock import MagicMock

import pytest

from app.services.category_matcher import CategoryMatcher


class FakeCategory:
    def __init__(self, name, description=None, category_type="expense"):
        self.name = name
        self.description = description
        self.category_type = category_type


def test_render_category_list_with_descriptions():
    m = CategoryMatcher.__new__(CategoryMatcher)  # avoid __init__ for this unit test
    cats = [
        FakeCategory("Side Projects", "Tools used for side projects (Cloudflare, Framer)"),
        FakeCategory("Food & Dining", None),
    ]
    rendered = m._render_category_list(cats)
    assert "- Side Projects — Tools used for side projects (Cloudflare, Framer)" in rendered
    assert "- Food & Dining" in rendered
    assert "None" not in rendered


def test_render_category_list_truncates_long_description():
    m = CategoryMatcher.__new__(CategoryMatcher)
    long = "A" * 500
    rendered = m._render_category_list([FakeCategory("X", long)])
    assert len(rendered) < 300  # bound: name + " — " + 200 chars max
```

- [ ] **Step 2: Run test**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py::test_render_category_list_with_descriptions -v`
Expected: FAIL.

- [ ] **Step 3: Add helper method**

In `backend/app/services/category_matcher.py`, inside `class CategoryMatcher`, near the other `_` helpers (e.g., after `_normalize_text`):

```python
    MAX_CATEGORY_DESCRIPTION_LEN = 200

    def _render_category_list(self, categories) -> str:
        """Render the category list for the LLM prompt, with truncated descriptions."""
        lines = []
        for cat in categories:
            desc = (cat.description or "").strip()
            if desc:
                if len(desc) > self.MAX_CATEGORY_DESCRIPTION_LEN:
                    desc = desc[: self.MAX_CATEGORY_DESCRIPTION_LEN].rstrip() + "…"
                lines.append(f"- {cat.name} — {desc}")
            else:
                lines.append(f"- {cat.name}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/category_matcher.py backend/tests/test_category_matcher_prompt.py
git commit -m "feat(categorizer): add _render_category_list helper with truncated descriptions"
```

---

## Task 5: Wire `_render_category_list` into both LLM prompt functions

**Files:**
- Modify: `backend/app/services/category_matcher.py:736-737, 894-895`

- [ ] **Step 1: Replace prompt category-list construction**

In `match_category_llm` (around line 736) and `_match_category_llm_with_details` (around line 894), replace:

```python
category_list = "\n".join([f"- {cat.name}" for cat in relevant_categories])
```

with:

```python
category_list = self._render_category_list(relevant_categories)
```

- [ ] **Step 2: Write assertion test**

Append to `backend/tests/test_category_matcher_prompt.py`:

```python
def test_prompt_includes_category_descriptions(monkeypatch, db_session):
    # Use the real CategoryMatcher with a stub DB; assert prompt contains descriptions.
    # This test builds the prompt by calling into match_category_llm up to (not through)
    # the OpenAI client call, using a monkeypatched _get_openai_client that raises to
    # short-circuit — then we inspect the prompt captured via a side effect.
    import app.services.category_matcher as cm_module
    captured = {}

    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["messages"] = kwargs["messages"]
                    class R:
                        class choices:
                            class _C:
                                class message:
                                    content = "UNKNOWN"
                            pass
                        choices = [type("X", (), {"message": type("M", (), {"content": "UNKNOWN"})()})()]
                        usage = type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})()
                    return R()

    m = cm_module.CategoryMatcher(db=db_session, user_id="prompt-user")
    monkeypatch.setattr(m, "_get_openai_client", lambda: StubClient())

    cats = [FakeCategory("Side Projects", "Tools like Cloudflare, Framer, GitHub.")]
    m.match_category_llm(
        description="Cloudflare workers",
        merchant="Cloudflare",
        amount=-5.0,
        available_categories=cats,
    )
    prompt_text = captured["messages"][1]["content"]
    assert "Side Projects — Tools like Cloudflare" in prompt_text
```

- [ ] **Step 3: Run tests**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/category_matcher.py backend/tests/test_category_matcher_prompt.py
git commit -m "feat(categorizer): render category descriptions in LLM prompt"
```

---

## Task 6: `_build_account_context` helper (SYL-29)

**Files:**
- Modify: `backend/app/services/category_matcher.py`
- Test: `backend/tests/test_category_matcher_prompt.py`

- [ ] **Step 1: Write failing tests**

Append:

```python
class FakeAccount:
    def __init__(self, name, external_id=None, alias_patterns=None):
        self.name = name
        self.external_id = external_id
        self.alias_patterns = alias_patterns or []


def test_account_context_empty_returns_empty_string():
    m = CategoryMatcher.__new__(CategoryMatcher)
    m._account_cache = []
    assert m._build_account_context() == ""


def test_account_context_with_last_four_and_patterns():
    m = CategoryMatcher.__new__(CategoryMatcher)
    m._account_cache = [
        FakeAccount("ABN AMRO checking", external_id="NL91ABNA0417164300"),
        FakeAccount(
            "Revolut Pro",
            external_id=None,
            alias_patterns=["Apple Pay Top-Up by *1234", "Revo Pro"],
        ),
    ]
    ctx = m._build_account_context()
    assert "Your accounts" in ctx
    assert "ABN AMRO checking (ends in 4300)" in ctx
    assert 'Revolut Pro (patterns: "Apple Pay Top-Up by *1234", "Revo Pro")' in ctx
```

- [ ] **Step 2: Run tests**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py -k account_context -v`
Expected: FAIL.

- [ ] **Step 3: Add helper and loader**

In `backend/app/services/category_matcher.py`:

1. Add an import if not present: `from app.models import Account`.
2. In `__init__`, initialize `self._account_cache: Optional[list] = None`.
3. Add two new methods:

```python
    def _load_accounts(self) -> list:
        if self._account_cache is not None:
            return self._account_cache
        from app.models import Account  # local import if global causes circularity
        accounts = (
            self.db.query(Account)
            .filter(Account.user_id == self.user_id, Account.is_active == True)
            .all()
        )
        self._account_cache = accounts
        return accounts

    def _build_account_context(self) -> str:
        accounts = self._account_cache if self._account_cache is not None else self._load_accounts()
        if not accounts:
            return ""
        lines = ["Your accounts (transactions referencing these are internal transfers):"]
        for acc in accounts:
            identifiers = []
            ext = (getattr(acc, "external_id", None) or "").strip()
            if ext and len(ext) >= 4:
                identifiers.append(f"ends in {ext[-4:]}")
            patterns = getattr(acc, "alias_patterns", None) or []
            if patterns:
                quoted = ", ".join(f'"{p}"' for p in patterns)
                identifiers.append(f"patterns: {quoted}")
            suffix = f" ({'; '.join(identifiers)})" if identifiers else ""
            lines.append(f"- {acc.name}{suffix}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py -k account_context -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/category_matcher.py backend/tests/test_category_matcher_prompt.py
git commit -m "feat(categorizer): add _build_account_context helper for transfer detection"
```

---

## Task 7: Inject account context + transfer rule into the prompt

**Files:**
- Modify: `backend/app/services/category_matcher.py` — prompt assembly in `match_category_llm` and `_match_category_llm_with_details`.

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_category_matcher_prompt.py`:

```python
def test_prompt_includes_account_context_and_transfer_rule(monkeypatch, db_session):
    import app.services.category_matcher as cm_module
    from app.models import Account
    captured = {}

    class StubClient:
        @staticmethod
        def _make():
            return type("R", (), {
                "choices": [type("X", (), {"message": type("M", (), {"content": "UNKNOWN"})()})()],
                "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
            })

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["messages"] = kwargs["messages"]
                    return StubClient._make()

    m = cm_module.CategoryMatcher(db=db_session, user_id="tr-user")
    monkeypatch.setattr(m, "_get_openai_client", lambda: StubClient())
    m._account_cache = [
        FakeAccount("Revolut Pro", alias_patterns=["Apple Pay Top-Up by *1234"])
    ]
    cats = [FakeCategory("Transfers", "Internal transfers", category_type="transfer")]
    m.match_category_llm(
        description="Apple Pay Top-Up by *1234",
        merchant="Revolut",
        amount=-50.0,
        available_categories=cats,
    )
    prompt = captured["messages"][1]["content"]
    assert "Your accounts" in prompt
    assert "Apple Pay Top-Up by *1234" in prompt
    assert "internal transfer" in prompt.lower()
```

- [ ] **Step 2: Run test**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py::test_prompt_includes_account_context_and_transfer_rule -v`
Expected: FAIL.

- [ ] **Step 3: Modify prompt assembly in both LLM functions**

In `match_category_llm` (around line 754) and `_match_category_llm_with_details` (around line 912), replace the prompt-building section:

```python
        prompt = f"""Categorize this financial transaction by selecting the most appropriate category.

Transaction details:
- Description: {description or 'N/A'}
- Merchant: {merchant or 'N/A'}
- Amount: {abs(amount)} {transaction_type_str.upper()}
- Type: {transaction_type_str}

Available categories:
{category_list}
{overrides_text}{instructions_text}
Instructions:
1. Analyze the transaction description and merchant name
2. Select the MOST SPECIFIC category that matches
3. Follow any user-specific guidelines and override patterns provided above
4. If the transaction matches a user override pattern, use that category
5. Respond with ONLY the exact category name from the list
6. If no category fits well, respond with "UNKNOWN"

Category name:"""
```

with:

```python
        account_context = self._build_account_context()
        account_block = f"\n\n{account_context}\n" if account_context else ""
        transfer_rule = (
            "If the transaction description, merchant, or counterparty references any of the "
            "accounts listed in \"Your accounts\", treat it as an internal transfer and pick the "
            "transfer category.\n" if account_context else ""
        )
        prompt = f"""Categorize this financial transaction by selecting the most appropriate category.

Transaction details:
- Description: {description or 'N/A'}
- Merchant: {merchant or 'N/A'}
- Amount: {abs(amount)} {transaction_type_str.upper()}
- Type: {transaction_type_str}

Available categories:
{category_list}
{account_block}{overrides_text}{instructions_text}
Instructions:
1. Analyze the transaction description and merchant name
2. Select the MOST SPECIFIC category that matches
3. {transfer_rule}4. Follow any user-specific guidelines and override patterns provided above
5. If the transaction matches a user override pattern, use that category
6. Respond with ONLY the exact category name from the list
7. If no category fits well, respond with "UNKNOWN"

Category name:"""
```

(The transfer rule slots in at step 3; subsequent steps renumber to 4-7.)

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/category_matcher.py backend/tests/test_category_matcher_prompt.py
git commit -m "feat(categorizer): inject account graph and transfer rule into LLM prompt"
```

---

## Task 8: Prompt-size budget cap

**Files:**
- Modify: `backend/app/services/category_matcher.py`
- Test: `backend/tests/test_category_matcher_prompt.py`

- [ ] **Step 1: Write failing test**

Append:

```python
def test_prompt_budget_degrades_descriptions_first():
    m = CategoryMatcher.__new__(CategoryMatcher)
    # Simulate oversized input: 30 categories each with a 200-char description.
    cats = [FakeCategory(f"Cat{i}", "x" * 200) for i in range(30)]
    m._account_cache = [FakeAccount("Acc", alias_patterns=["p1", "p2"])]
    category_list, account_block = m._compose_prompt_context(cats)
    assert sum(len(x) for x in (category_list, account_block)) <= 2000
    # Descriptions dropped, but names always present
    assert "Cat0" in category_list
    assert "Cat29" in category_list
```

- [ ] **Step 2: Run test**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py::test_prompt_budget_degrades_descriptions_first -v`
Expected: FAIL.

- [ ] **Step 3: Implement `_compose_prompt_context`**

In `CategoryMatcher`:

```python
    PROMPT_CONTEXT_BUDGET = 2000

    def _compose_prompt_context(self, relevant_categories) -> tuple[str, str]:
        """Return (category_list, account_block) sized to fit PROMPT_CONTEXT_BUDGET.

        Degradation order when over budget:
        1. Truncate each category description to 200 chars (default).
        2. Drop alias_patterns from accounts (keep name + ends-in).
        3. Drop all descriptions; names only.
        """
        category_list = self._render_category_list(relevant_categories)
        account_block = self._build_account_context()
        total = len(category_list) + len(account_block)
        if total <= self.PROMPT_CONTEXT_BUDGET:
            return category_list, f"\n\n{account_block}\n" if account_block else ""

        # Step 2: drop alias_patterns
        if self._account_cache:
            thin_accounts = []
            for acc in self._account_cache:
                identifiers = []
                ext = (getattr(acc, "external_id", None) or "").strip()
                if ext and len(ext) >= 4:
                    identifiers.append(f"ends in {ext[-4:]}")
                suffix = f" ({'; '.join(identifiers)})" if identifiers else ""
                thin_accounts.append(f"- {acc.name}{suffix}")
            thin_account_block = (
                "Your accounts (transactions referencing these are internal transfers):\n"
                + "\n".join(thin_accounts)
            )
        else:
            thin_account_block = ""
        total = len(category_list) + len(thin_account_block)
        if total <= self.PROMPT_CONTEXT_BUDGET:
            return category_list, f"\n\n{thin_account_block}\n" if thin_account_block else ""

        # Step 3: drop all descriptions
        name_only = "\n".join(f"- {c.name}" for c in relevant_categories)
        return name_only, f"\n\n{thin_account_block}\n" if thin_account_block else ""
```

- [ ] **Step 4: Use it in both LLM functions**

Replace the two lines:

```python
        category_list = self._render_category_list(relevant_categories)
        account_context = self._build_account_context()
        account_block = f"\n\n{account_context}\n" if account_context else ""
```

with:

```python
        category_list, account_block = self._compose_prompt_context(relevant_categories)
```

Note: `transfer_rule` should still check truthiness of `account_block`.

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/category_matcher.py backend/tests/test_category_matcher_prompt.py
git commit -m "feat(categorizer): enforce 2000-char prompt budget with graceful degradation"
```

---

## Task 9: Feature flag `CATEGORIZER_ENRICHED_PROMPT`

**Files:**
- Modify: `backend/app/services/category_matcher.py`

- [ ] **Step 1: Add env-var gated branch**

At the top of `category_matcher.py` with other module-level config:

```python
import os

ENRICHED_PROMPT_ENABLED = os.getenv("CATEGORIZER_ENRICHED_PROMPT", "true").lower() == "true"
```

In both LLM prompt functions, replace:

```python
        category_list, account_block = self._compose_prompt_context(relevant_categories)
```

with:

```python
        if ENRICHED_PROMPT_ENABLED:
            category_list, account_block = self._compose_prompt_context(relevant_categories)
        else:
            category_list = "\n".join(f"- {c.name}" for c in relevant_categories)
            account_block = ""
```

And wrap the transfer-rule injection with `if ENRICHED_PROMPT_ENABLED and account_block:` instead of just `if account_context:`.

- [ ] **Step 2: Add regression test**

Append to `backend/tests/test_category_matcher_prompt.py`:

```python
def test_feature_flag_disabled_falls_back_to_names_only(monkeypatch, db_session):
    import app.services.category_matcher as cm_module
    monkeypatch.setattr(cm_module, "ENRICHED_PROMPT_ENABLED", False)
    captured = {}

    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    captured["messages"] = kwargs["messages"]
                    return type("R", (), {
                        "choices": [type("X", (), {"message": type("M", (), {"content": "UNKNOWN"})()})()],
                        "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
                    })

    m = cm_module.CategoryMatcher(db=db_session, user_id="ff-user")
    monkeypatch.setattr(m, "_get_openai_client", lambda: StubClient())
    m._account_cache = [FakeAccount("Acc", alias_patterns=["p"])]
    cats = [FakeCategory("Food", "Description here")]
    m.match_category_llm(description="x", merchant="y", amount=-1.0, available_categories=cats)
    prompt = captured["messages"][1]["content"]
    assert "Description here" not in prompt
    assert "Your accounts" not in prompt
```

- [ ] **Step 3: Run tests**

Run: `cd backend && pytest tests/test_category_matcher_prompt.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/category_matcher.py backend/tests/test_category_matcher_prompt.py
git commit -m "feat(categorizer): add CATEGORIZER_ENRICHED_PROMPT feature flag"
```

---

## Task 10: End-to-end transfer-detection test with stubbed OpenAI

**Files:**
- Create: `backend/tests/test_category_matcher_llm_transfer.py`

- [ ] **Step 1: Write the test**

```python
"""Verify that with an alias-matched account, the LLM prompt steers toward the transfer category."""
from decimal import Decimal

import pytest

from app.services.category_matcher import CategoryMatcher


class FakeCategory:
    def __init__(self, name, category_type="expense"):
        self.name = name
        self.category_type = category_type
        self.description = None


class FakeAccount:
    def __init__(self, name, alias_patterns=None):
        self.name = name
        self.external_id = None
        self.alias_patterns = alias_patterns or []
        self.is_active = True


def test_llm_selects_transfers_when_alias_matches(monkeypatch, db_session):
    import app.services.category_matcher as cm_module
    monkeypatch.setattr(cm_module, "ENRICHED_PROMPT_ENABLED", True)

    class StubClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    # The stub "reads" the prompt: if it mentions the alias + transfer rule,
                    # return the transfer category name.
                    content = kwargs["messages"][1]["content"]
                    if "Apple Pay Top-Up by *1234" in content and "internal transfer" in content.lower():
                        answer = "Transfers"
                    else:
                        answer = "UNKNOWN"
                    return type("R", (), {
                        "choices": [type("X", (), {"message": type("M", (), {"content": answer})()})()],
                        "usage": type("U", (), {"prompt_tokens": 1, "completion_tokens": 1})(),
                    })

    m = CategoryMatcher(db=db_session, user_id="llm-user")
    monkeypatch.setattr(m, "_get_openai_client", lambda: StubClient())
    m._account_cache = [FakeAccount("Revolut Pro", alias_patterns=["Apple Pay Top-Up by *1234"])]
    cats = [FakeCategory("Transfers", category_type="transfer"), FakeCategory("Food & Dining")]
    result = m.match_category_llm(
        description="Apple Pay Top-Up by *1234",
        merchant="Revolut",
        amount=-50.0,
        available_categories=cats,
    )
    assert result == "Transfers"
```

- [ ] **Step 2: Run the test**

Run: `cd backend && pytest tests/test_category_matcher_llm_transfer.py -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_category_matcher_llm_transfer.py
git commit -m "test(categorizer): verify alias-matched transfer is recognized at inference time"
```

---

## Task 11: Observability logs

**Files:**
- Modify: `backend/app/services/category_matcher.py`

- [ ] **Step 1: Log context lengths**

In both LLM prompt functions, immediately after `category_list, account_block = ...`:

```python
        logger.debug(
            "categorizer.prompt_context chars: categories=%d accounts=%d total=%d",
            len(category_list), len(account_block),
            len(category_list) + len(account_block),
        )
        if len(category_list) + len(account_block) >= self.PROMPT_CONTEXT_BUDGET:
            logger.info("categorizer.prompt_budget_hit user_id=%s", self.user_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/category_matcher.py
git commit -m "chore(categorizer): log prompt-context sizes and budget hits"
```

---

## Self-Review Checklist

- Spec coverage: Section A (Tasks 4-5), Section B (Tasks 6-7), Section C (Tasks 1-3), Section D (Task 8), Section E (Tasks 5, 7, 10), Section F (Tasks 9, 11). ✅
- Placeholder scan: none.
- Type consistency: `FakeCategory`, `FakeAccount` defined in Task 4 and 6 tests; shared helpers re-declared in later test files for isolation — intentional, each test file is self-contained per the "no cross-file fixture imports" convention in this repo's tests directory.
- `_compose_prompt_context` always returns `(category_list, account_block)`; both callers use tuple unpacking.
- `_account_cache` initialized in `__init__`; never `None` when reached via `_build_account_context` because `_load_accounts` is called lazily.
