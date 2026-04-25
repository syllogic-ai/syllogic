# MCP Tool Enhancements for Categorization Audits

**Date:** 2026-04-24
**Tickets:** SYL-30, SYL-31, SYL-33
**Status:** Draft

## Context

Bulk categorization sessions on the Syllogic MCP server have surfaced three classes of friction:

- **SYL-30** — `search_transactions_multi` silently truncates at 1000 rows with no pagination. Existing `list_transactions` / `search_transactions` have no sort capability and `search_transactions_multi` has no `account_id` filter.
- **SYL-31** — There is no first-class way to audit miscategorized data. Agents cannot easily ask "what are the biggest items in Other Expenses?" or "which merchants appear most without a category?" via existing tools.
- **SYL-33** — `bulk_update_transaction_categories` mutates immediately with no preview, no undo, and the response drops silently-invalid IDs in some cases.

SYL-32's MCP write path and SYL-34 are already handled by the `update_category` tool shipped in commit d09639f. SYL-29 and SYL-32's pipeline piece are deferred to Spec 2 (AI categorizer).

## Goals

- Safer and more efficient bulk categorization audits and updates.
- **Zero new MCP tools.** Every change is a parameter addition to an existing tool.
- Fully backward compatible — existing agent call signatures continue to work unchanged.

## Non-Goals

- Embedding-based categorization (SYL-28).
- Category editing via MCP (already shipped).
- AI categorizer prompt changes (Spec 2).

## Design

### Section A — SYL-30: Cursor pagination, sort_by, account_id filter

**Tools touched:** `search_transactions`, `search_transactions_multi`, `list_transactions` (all in `backend/app/mcp/tools/transactions.py`).

1. **Cursor pagination — additive.** Add `cursor: Optional[str]` param alongside existing `page` param on `search_transactions` and `list_transactions`. When `cursor` is provided, `page` is ignored. The cursor is an opaque base64-encoded `(booked_at_iso, id_uuid)` tuple that is stable under concurrent inserts. On `search_transactions_multi`, which has no pagination today, cursor mode is opt-in: default behavior (return up to `max_results` capped at 1000) is preserved.
2. **`sort_by` on all three tools.** `Literal["booked_at_desc", "booked_at_asc", "amount_desc", "amount_asc", "abs_amount_desc"]`. Default: `booked_at_desc` — preserves current behavior. The cursor payload encodes the sort key's value plus the UUID tiebreaker to guarantee deterministic pagination across any sort order.
3. **`account_id` filter on `search_transactions` and `search_transactions_multi`.** `list_transactions` already has it.
4. **Response shape.** Add `next_cursor: Optional[str]` to the response. Present iff more results exist under the current filter/sort. Existing `page`, `has_more`, `total_count` fields remain for callers using page mode.

**Shared helper.** A new internal `_paginate_query(query, cursor, sort_by, limit)` function in `transactions.py` used by all three tools. Eliminates duplicated sort/cursor logic and keeps behavior identical.

### Section B — SYL-31: Audit filters

**Tools touched:** `list_transactions`, `get_spending_by_category`, `get_top_merchants`.

1. **`list_transactions`:**
   - `uncategorized: bool = False` — matches rows where both `category_id IS NULL` and `category_system_id IS NULL`.
   - `category_type: Optional[Literal["expense", "income", "transfer"]]` — joins on `Category.category_type` through either `category_id` or `category_system_id`.
2. **`get_spending_by_category`:**
   - `include_uncategorized: bool = False` — switches the inner-join on categories to a left-join and surfaces null-category rows as `{category_id: null, category_name: "Uncategorized", ...}`.
   - Every row gains `merchant_count` (distinct non-null merchants in that category).
3. **`get_top_merchants`:**
   - `category_id: Optional[str]` — scope to a single category (e.g., "top merchants in Other Expenses").
   - `uncategorized: bool = False` — top merchants that have no category assigned. Mutually exclusive with `category_id`; return error if both are set.

Together these deliver the two core audit queries ("biggest miscategorized items" and "most frequent uncategorized merchants") without adding a new tool.

### Section C — SYL-33: Dry-run and improved response on bulk_update

**Tool touched:** `bulk_update_transaction_categories`.

1. **`dry_run: bool = False`.** When true, run the same WHERE query the mutation would use and return exactly what *would* change, without committing. No DB write.
2. **Response upgrade**, applied to both dry-run and real-run:
   - `updated_count` (or `would_update_count` when `dry_run=true`)
   - `requested_count` — number of IDs the caller passed
   - `invalid_ids: list[str]` — malformed UUIDs (already present)
   - `not_found_ids: list[str]` — valid UUIDs that don't belong to the caller's transactions (**new**; previously silently dropped)
   - `skipped_already_in_category_ids: list[str]` — IDs already assigned to the target category (**new**; no-op updates)
   - `sample_changes: list[{id, description, merchant, amount, previous_category_name}]` — up to 10 entries, for agent transparency before/after confirmation
3. **Hard cap.** `max 2000 transaction_ids per call`. Return a clear error if exceeded. Protects against runaway miscategorizations during a single agent session.

### Section D — Testing

- Unit tests per tool covering:
  - Cursor round-trip (first page → `next_cursor` → second page → no overlap, no gap).
  - Each `sort_by` ordering on a seeded transaction set.
  - `uncategorized` filter excludes system-assigned categories only when both `category_id` and `category_system_id` are null.
  - `dry_run` preview matches what a subsequent real run actually changes.
- Integration test in `tests/test_mcp_bulk_update.py` that seeds ~50 transactions with mixed valid/invalid/foreign/same-category IDs and asserts every response field is populated correctly for both dry-run and real-run.

### Section E — Backward compatibility

- All new parameters default to the existing behavior. No call signature changes.
- Response objects gain new fields; no fields are removed or renamed.
- Docstrings updated with usage examples so agents discover the new params. The MCP server's tool description is the documentation surface.

## Open Questions

None at present.

## References

- `backend/app/mcp/tools/transactions.py`
- `backend/app/mcp/tools/categories.py`
- `backend/app/mcp/tools/analytics.py`
- Commit `d09639f` — `update_category` (prior work that resolved SYL-34 and SYL-32's MCP-write piece).
