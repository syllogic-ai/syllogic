# AI Categorizer Prompt Enrichment

**Date:** 2026-04-24
**Tickets:** SYL-29 (pipeline piece), SYL-32 (prompt piece)
**Status:** Draft

## Context

The LLM categorizer in `backend/app/services/category_matcher.py` builds its prompt with category **names only** and no awareness of the user's own accounts. Two classes of failure follow:

- **SYL-32** — Custom categories like "Side Projects" and Greek transliterations like "Efood" / "Sklavenitis" / "Paradosiako" have no training signal, so they consistently land in "Other Expenses".
- **SYL-29** — Internal transfers (~1,000 transactions, €200K+ in movement) are systematically miscategorized. The post-hoc `InternalTransferService` catches pair-matched cases but misses single-sided references like `Apple Pay Top-Up by *1234` or `Revo Pro`, because the AI at inference time has no knowledge of the user's account graph.

Both problems are solved at the same surface: the prompt that goes into `match_category_llm` and `_match_category_llm_with_details`.

## Goals

- Give the LLM enough context to pick custom and non-English categories correctly on first pass.
- Catch single-sided internal transfers at inference time, without replacing the existing post-hoc pair-matcher.
- Keep changes minimal, additive, and safely bounded in prompt size.

## Non-Goals

- Retroactive recategorization of existing transactions (a separate one-off migration, not this spec).
- Changes to `InternalTransferService` post-hoc pair matching — it continues to run and remains complementary.
- Embedding-based retrieval (SYL-28, deferred).
- UI for editing `alias_patterns` (separate follow-up ticket).

## Design

### Section A — SYL-32: Pass category descriptions to the LLM

**File touched:** `backend/app/services/category_matcher.py`, functions `match_category_llm` (line ~683) and `_match_category_llm_with_details` (line ~842).

Replace the flat category list:

```
- Side Projects
- Food & Dining
- Other Expenses
```

with a description-enriched list:

```
- Side Projects — Tools and services for personal side projects (Cloudflare, Framer, Moneybird, GitHub, OpenAI API)
- Food & Dining — Restaurants, takeaway, and groceries (Efood, Paradosiako, Sklavenitis)
- Other Expenses — Use only as a last resort when no other category fits
```

Descriptions are read from the existing `Category.description` column (surfaced via `list_categories`, editable via `update_category`). Truncate each description to **200 chars** before emission. If a description is empty, emit the category name alone — preserves current behavior.

### Section B — SYL-29: Inject account graph into the prompt

**File touched:** same file, same two functions. New private helper `_build_account_context(self) -> str`.

Before the `Instructions` block, insert a "Your accounts" section listing the user's own accounts with enough identifying metadata for the LLM to spot references, and add one explicit rule to the numbered instructions:

> If the transaction description, merchant, or counterparty references any of the accounts listed in "Your accounts", the transaction is an **internal transfer** — choose the transfer category.

Block format:

```
Your accounts (transactions referencing these are internal transfers):
- ABN AMRO checking (ends in 6789)
- Revolut Pro (patterns: "Apple Pay Top-Up by *1234", "Revo Pro", "Nlov*")
- Wise EUR (ends in 4321)
```

The helper queries `Account` for `self.user_id`, caches results on the service instance analogous to `_category_cache`, and formats each row from: `Account.name`, last-4 of account number where available, and the new `alias_patterns` field (Section C). Accounts with no distinguishing metadata contribute `name` only.

### Section C — Data model addition

- **Migration:** add `alias_patterns JSONB NOT NULL DEFAULT '[]'::jsonb` to the `accounts` table. Uses Alembic (see existing `backend/postgres_migration/` conventions).
- **Model:** add `alias_patterns: Mapped[list[str]]` to `Account` in `backend/app/models.py` with `default=list`.
- **Schema:** expose in `AccountRead` / `AccountUpdate` Pydantic schemas.
- **API surface:** allow updating `alias_patterns` via the existing account update endpoint.
- **No dedicated UI** in this spec.

### Section D — Prompt budget & safety

Cap total injected dynamic context (category descriptions + account block) at **~2000 characters**. If over budget, degrade gracefully:

1. Truncate each description to 200 chars (baseline).
2. If still over budget, drop alias pattern lists (keep account name + last-4 only).
3. If still over budget, drop descriptions entirely and fall back to current behavior.

Category names and the transfer-detection rule are always present — they are the load-bearing additions.

### Section E — Testing

New tests under `backend/tests/`:

- `test_category_matcher_prompt.py`:
  - `_build_account_context` with: no accounts, accounts without last-4, accounts with `alias_patterns`, accounts with both.
  - Assembled prompt contains each category's description when present.
  - Assembled prompt contains "Your accounts" block when accounts exist, and the transfer rule line.
  - Snapshot test of the full prompt for a representative input — makes future phrasing changes intentional.
  - Prompt budget: when >2000 chars of context, degradation order matches Section D.
- `test_category_matcher_llm_transfer.py`:
  - Stub OpenAI client; synthetic transaction `"Apple Pay Top-Up by *1234"` with a matching account alias → transfer category selected.

### Section F — Rollout

- Feature-flag behind an env var `CATEGORIZER_ENRICHED_PROMPT=true` (default true in dev, opt-in in prod for one release cycle), so regressions can be reverted without redeploy.
- Log prompt length and injected-context length at DEBUG; add a counter for prompts that hit the 2000-char budget cap.

## Open Questions

None at present.

## References

- `backend/app/services/category_matcher.py` — prompt assembly in `match_category_llm` (line ~683) and `_match_category_llm_with_details` (line ~842).
- `backend/app/services/internal_transfer_service.py` — complementary post-hoc pair matcher, unchanged.
- `backend/app/models.py` — `Account` and `Category` models.
- Commit `d09639f` — `update_category` MCP tool, write path for `Category.description`.
