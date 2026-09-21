"""Stage 2 of the receipt-ingestion pipeline: categorization.

Text-only. Input is the extracted lines of an already-validated receipt plus
the user's expense-category tree; output is exactly one category per line
and nothing else -- no totals, no merges, no splits. See
docs/specs/receipt-ingestion.md Part 5 and
docs/specs/receipt-ingestion-implementation.md 5.2.

**Why not `CategoryMatcher`.** `CategoryMatcher` (`category_matcher.py`) is
built for a single bank transaction -- one description, one merchant, one
amount, with a keyword tier ahead of the LLM. A receipt is ~15 lines sharing
one merchant, where the useful signal is cross-line context: the model
should see the whole basket at once. Fifteen independent `match_category`
calls would throw that context away and cost more than one call that sees
everything.

**Enforcement lives in code, not the prompt.** The model is asked nicely to
behave; none of that is trusted. After the call:

1. Every line_id supplied must appear in the response exactly once. Missing
   or duplicated is `ReceiptCategorizationError`, not a partial result.
2. Every `category_id` returned must be one of the ids actually offered. One
   outside that set raises -- it never silently falls through to
   "uncategorized", which would look like a successful categorization.
3. A `kind="deposit"` line's category is overwritten with its parent item's
   resolved assignment regardless of what the model said for it. The model
   is still asked for one (so schema enforcement in (1) covers it too), but
   its answer for that line is discarded.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Sequence
from uuid import UUID

from sqlalchemy.orm import Session

from app.services import category_tree
from app.services.llm_client import create_llm_clients
from app.services.llm_structured import call_structured

logger = logging.getLogger(__name__)

CATEGORY_CONFIDENCE_VALUES = ("high", "medium", "low")

_SCHEMA_NAME = "receipt_categorization"

CATEGORIZE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assignments"],
    "properties": {
        "assignments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["line_id", "category_id", "confidence", "reason"],
                "properties": {
                    "line_id": {"type": "string"},
                    "category_id": {"type": "string"},
                    "confidence": {"type": "string", "enum": list(CATEGORY_CONFIDENCE_VALUES)},
                    "reason": {"type": "string"},
                },
            },
        }
    },
}

# Transcription-only in stage 1's sense of "the model must not do the parts
# that are code's job" -- here that means no totals, no grouping, no
# deciding how many transactions result. Only "which one category" per line.
CATEGORIZE_SYSTEM_PROMPT = """You assign exactly one category to each line of a retail receipt. You do \
not total anything, you do not group lines together, and you do not decide \
how many transactions result -- all of that happens later, in code, from \
your per-line answers.

Rules:
- Return exactly one assignment per line_id given to you. No more, no fewer.
- `category_id` must be copied verbatim from the "id" field of one of the \
supplied categories. Never invent an id and never omit a line -- if nothing \
fits well, choose the closest category and set `confidence` to "low" rather \
than leaving the line out.
- Categorize each line on its own merits -- what the item is, not what the \
whole receipt was for. A single pastry on an otherwise all-groceries receipt \
is a dining/treats category if one exists, even though every other line is \
groceries.
- Each category may carry `categorization_instructions` -- the user's own \
rule for what belongs there. Follow it; it is more specific than your own \
judgment.
- `confidence` is "high", "medium" or "low". Use "low" whenever a line could \
reasonably sit in two different categories -- hedging costs nothing here, \
and low-confidence lines are shown to the user for review, so it is strictly \
more useful than a confident guess.
- `reason` is one short clause explaining the choice -- not a restatement of \
the line's name.
- A packaging-deposit line ("kind": "deposit") should get the same category \
as the item it belongs to; it is fine either way, because the final answer \
for a deposit line is always taken from its parent item in code, not from \
you.

Respond with ONLY the JSON object -- no prose, no code fence."""


class ReceiptCategorizationError(RuntimeError):
    """Raised when the model's assignments can't be trusted as-is: a missing
    or duplicated line_id, an unrecognized category_id, or an unresolvable
    deposit parent. Never caught to produce a partial or "uncategorized"
    result -- that would look like a successful categorization when it
    isn't one."""


@dataclass(frozen=True)
class CategorizableLine:
    """The minimal per-line shape stage 2 needs. Deliberately not the ORM
    `ReceiptLineItem` -- this module, and its tests, have no need of a
    database or a receipt scan, only these four fields."""

    line_ref: str
    name: str | None
    raw_text: str | None
    kind: str  # "item" | "deposit"
    parent_line_ref: str | None


@dataclass(frozen=True)
class LineCategoryAssignment:
    line_ref: str
    category_id: UUID
    confidence: str
    reason: str


def _build_messages(lines: Sequence[CategorizableLine], categories_json: str) -> list[dict]:
    lines_payload = [
        {
            "line_id": line.line_ref,
            "name": line.name or line.raw_text or "",
            "kind": line.kind,
        }
        for line in lines
    ]
    user_content = (
        "Categories you may assign (id, name, and the user's own "
        "categorization_instructions where present):\n"
        f"{categories_json}\n\n"
        "Receipt lines to categorize:\n"
        f"{json.dumps(lines_payload, indent=2)}"
    )
    return [
        {"role": "system", "content": CATEGORIZE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _assign_categories(
    lines: Sequence[CategorizableLine],
    payload: dict,
    valid_category_ids: set[str],
) -> dict[str, LineCategoryAssignment]:
    """Pure enforcement: no DB, no LLM call. Raises `ReceiptCategorizationError`
    rather than returning a partial result. Exposed at module level
    (not nested) specifically so it can be unit-tested against a raw payload
    dict without mocking an LLM call at all."""
    assignments_raw = payload.get("assignments") or []

    by_line_id: dict[str, dict] = {}
    for entry in assignments_raw:
        line_id = str(entry.get("line_id") or "")
        if line_id in by_line_id:
            raise ReceiptCategorizationError(
                f"Model returned more than one assignment for line_id {line_id!r}."
            )
        by_line_id[line_id] = entry

    expected_ids = {line.line_ref for line in lines}
    missing = expected_ids - set(by_line_id)
    extra = set(by_line_id) - expected_ids
    if missing:
        raise ReceiptCategorizationError(
            "Model omitted assignment(s) for line(s): " + ", ".join(sorted(missing))
        )
    if extra:
        raise ReceiptCategorizationError(
            "Model returned assignment(s) for unknown line(s): " + ", ".join(sorted(extra))
        )

    resolved: dict[str, LineCategoryAssignment] = {}
    for line in lines:
        entry = by_line_id[line.line_ref]
        category_id_raw = str(entry.get("category_id") or "")
        if category_id_raw not in valid_category_ids:
            raise ReceiptCategorizationError(
                f"Model assigned category_id {category_id_raw!r} to line "
                f"{line.line_ref!r}, which is not one of the supplied categories."
            )

        confidence = entry.get("confidence")
        if confidence not in CATEGORY_CONFIDENCE_VALUES:
            raise ReceiptCategorizationError(
                f"Model returned confidence {confidence!r} for line "
                f"{line.line_ref!r}; expected one of {CATEGORY_CONFIDENCE_VALUES}."
            )

        reason = str(entry.get("reason") or "").strip()
        resolved[line.line_ref] = LineCategoryAssignment(
            line_ref=line.line_ref,
            category_id=UUID(category_id_raw),
            confidence=confidence,
            reason=reason,
        )

    # Deposits inherit their parent item's assignment regardless of what the
    # model said for them -- enforced here, never left to the model (spec
    # 5.2 / implementation plan 5.2 item 3).
    for line in lines:
        if line.kind != "deposit":
            continue
        parent_assignment = resolved.get(line.parent_line_ref) if line.parent_line_ref else None
        if parent_assignment is None:
            # Should not happen downstream of `receipt_validate.validate`,
            # which flags an unresolvable deposit parent as `orphan_deposit`
            # and keeps the scan out of this stage entirely -- but this
            # module doesn't assume its caller enforced that, so it fails
            # loudly here too rather than leaving the deposit's category to
            # whatever the model guessed.
            raise ReceiptCategorizationError(
                f"Deposit line {line.line_ref!r} has no resolvable parent "
                f"({line.parent_line_ref!r}) to inherit a category from."
            )
        resolved[line.line_ref] = LineCategoryAssignment(
            line_ref=line.line_ref,
            category_id=parent_assignment.category_id,
            confidence=parent_assignment.confidence,
            reason=parent_assignment.reason,
        )

    return resolved


def categorize_lines(
    db: Session,
    user_id: str,
    lines: Sequence[CategorizableLine],
) -> dict[str, LineCategoryAssignment]:
    """Runs the stage-2 LLM call and enforcement, returning
    `{line_ref: LineCategoryAssignment}` for every line in `lines`.

    Text-only: requires only `{"strict_schema"}`, not vision. Raises
    `ReceiptCategorizationError` (enforcement) or whatever `call_structured`
    raises (`StructuredCallError`, `NoCapableProviderError`) on failure --
    there is no partial-result path.
    """
    if not lines:
        return {}

    categories_json = category_tree.serialize_for_prompt(
        db, user_id, types=frozenset({"expense"}), leaves_only=True
    )
    valid_category_ids = {node["id"] for node in json.loads(categories_json)}
    if not valid_category_ids:
        raise ReceiptCategorizationError(
            f"User {user_id} has no expense categories to assign receipt lines to."
        )

    providers = create_llm_clients(db, requires=frozenset({"strict_schema"}))
    messages = _build_messages(lines, categories_json)

    payload, _model = call_structured(
        providers,
        messages=messages,
        schema=CATEGORIZE_SCHEMA,
        schema_name=_SCHEMA_NAME,
        max_tokens=2000,
        timeout=45,
    )

    return _assign_categories(lines, payload, valid_category_ids)


def categorize_receipt_lines(db: Session, user_id: str, receipt_line_items: Sequence) -> None:
    """Convenience wrapper for `tasks/receipt_tasks.py`: takes the
    already-persisted `ReceiptLineItem` rows for one scan, runs
    `categorize_lines`, and writes `category_id`/`category_confidence`/
    `category_reason` directly onto those ORM objects. Does not commit --
    the caller owns the transaction.
    """
    if not receipt_line_items:
        return

    categorizable = [
        CategorizableLine(
            line_ref=item.line_ref,
            name=item.name,
            raw_text=item.raw_text,
            kind=item.kind,
            parent_line_ref=item.parent_line_ref,
        )
        for item in receipt_line_items
    ]

    assignments = categorize_lines(db, user_id, categorizable)

    by_ref = {item.line_ref: item for item in receipt_line_items}
    for line_ref, assignment in assignments.items():
        item = by_ref[line_ref]
        item.category_id = assignment.category_id
        item.category_confidence = assignment.confidence
        item.category_reason = assignment.reason
