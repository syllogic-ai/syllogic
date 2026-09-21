"""Shared category-tree serializer.

Moved out of `app/mcp/resources.py`, which used to build this walk in-line
for the `syllogic://categories` resource (querying via `category_tools`,
then annotating every node with `categorization_instructions` from
`category_tools.categorization_instructions_map`). Stage 2 of the
receipt-ingestion pipeline (`receipt_categorize.py`) needs the exact same
payload -- a category, its id, and the user's own categorization rules --
so this module gives both callers one walk instead of two that could drift.
See docs/specs/receipt-ingestion-implementation.md 5.1 and
docs/specs/receipt-ingestion.md Part 5.1.

Unlike the MCP tools under `app/mcp/tools/`, this module takes a `db`
Session rather than opening its own -- both callers (a Celery task and an
MCP resource handler) already have one open and this needs to compose into
either without a second connection.

`categorization_instructions` are included **verbatim**, never truncated or
summarized -- those strings are the user's own rules, and trimming them
degrades every categorization that reads them while leaving no trace of why.
"""

from __future__ import annotations

import json
from typing import FrozenSet
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Category

# Every `Category.category_type` value in the schema. Passed explicitly by
# the MCP resource, which (unlike stage 2) wants every type, not just
# expenses.
ALL_CATEGORY_TYPES: FrozenSet[str] = frozenset({"expense", "income", "transfer"})


def _base_node(category: Category, instructions: dict[str, str | None]) -> dict:
    return {
        "id": str(category.id),
        "name": category.name,
        "category_type": category.category_type,
        "color": category.color,
        "icon": category.icon,
        "description": category.description,
        "categorization_instructions": instructions.get(str(category.id)),
        "parent_id": str(category.parent_id) if category.parent_id else None,
        "is_system": category.is_system,
    }


def serialize_for_prompt(
    db: Session,
    user_id: str,
    *,
    types: FrozenSet[str] = frozenset({"expense"}),
    leaves_only: bool = True,
    exclude_category_ids: FrozenSet[UUID] = frozenset(),
) -> str:
    """Returns the user's category tree as a JSON string, annotated with
    each category's `categorization_instructions`.

    Args:
        types: only categories whose `category_type` is in this set are
            included. The MCP resource passes `ALL_CATEGORY_TYPES`; stage 2
            categorization wants `{"expense"}` only -- a receipt line is
            never an income or transfer category.
        leaves_only: when True, the result is a flat list of leaf categories
            only (no `children` key) -- what stage 2 needs, since only a
            leaf category is ever assignable to a line. When False (the MCP
            resource's case), the result is the full nested tree with
            `children` arrays, matching what `syllogic://categories` served
            before this module existed.
        exclude_category_ids: categories to drop regardless of type or leaf
            status. Unused by any caller today -- this is spec 8.2's hook
            (excluding a legacy/overlapping taxonomy from the prompt),
            shipped now as a real filter so that phase doesn't have to touch
            this signature.
    """
    categories = (
        db.query(Category).filter(Category.user_id == user_id).order_by(Category.name).all()
    )

    instructions = {str(c.id): c.categorization_instructions for c in categories}
    excluded = {str(cid) for cid in exclude_category_ids}

    children_count: dict[str, int] = {}
    for category in categories:
        parent_id = str(category.parent_id) if category.parent_id else None
        if parent_id:
            children_count[parent_id] = children_count.get(parent_id, 0) + 1

    if leaves_only:
        leaves = [
            _base_node(category, instructions)
            for category in categories
            if category.category_type in types
            and str(category.id) not in excluded
            and children_count.get(str(category.id), 0) == 0
        ]
        return json.dumps(leaves, indent=2)

    # Nested tree: only nodes matching `types`/`exclude_category_ids`
    # survive, but a surviving parent keeps only the children that
    # themselves survive the same filter.
    nodes: dict[str, dict] = {}
    for category in categories:
        if category.category_type not in types or str(category.id) in excluded:
            continue
        node = _base_node(category, instructions)
        node["children"] = []
        nodes[str(category.id)] = node

    roots: list[dict] = []
    for category in categories:
        cat_id = str(category.id)
        if cat_id not in nodes:
            continue
        parent_id = str(category.parent_id) if category.parent_id else None
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(nodes[cat_id])
        else:
            roots.append(nodes[cat_id])

    return json.dumps(roots, indent=2)
