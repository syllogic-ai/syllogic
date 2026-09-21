"""MCP resources: the things an agent should be able to read without a tool call.

A tool call is a question the agent has to know to ask. A resource is
context it can be handed. The four here are the things nearly every session
needs before it can do anything useful -- what accounts exist, what
categories exist, who is in the household, and what the numbers mean -- and
making each of them a tool call means every session spends its first three
round trips rediscovering the same facts.

`syllogic://schema` is the one that earns its place several times over. The
field semantics it states are currently spread across forty docstrings, and
the one that matters most -- `category_id` beats `category_system_id` -- is
mentioned in about three of them. An agent that gets that wrong produces
answers that are plausible, confident and wrong, which is the expensive kind.

Balances are deliberately *not* in `syllogic://accounts`. A resource is
cached, and a cached balance is stale by construction; "your balance is
X" where X is an hour old is worse than one more tool call. Names, ids,
types and currencies do not move, so those are here.
"""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from app.db_helpers import get_mcp_user_id
from app.mcp.dependencies import get_db
from app.mcp.tools import accounts as account_tools
from app.mcp.tools import people as people_tools
from app.services import category_tree


# (value, expires_at), keyed by (uri, user_id). Per-user because every one of
# these is scoped to the caller -- a shared cache here would be a data leak,
# not a performance win.
_cache: dict[tuple[str, str], tuple[Any, float]] = {}

ACCOUNTS_TTL = 300  # 5 minutes
CATEGORIES_TTL = 900  # 15 minutes
PEOPLE_TTL = 900  # 15 minutes


def _cached(uri: str, user_id: str, ttl: int, build: Callable[[], Any]) -> Any:
    key = (uri, user_id)
    hit = _cache.get(key)
    now = time.monotonic()
    if hit is not None and hit[1] > now:
        return hit[0]
    value = build()
    _cache[key] = (value, now + ttl)
    return value


def clear_cache() -> None:
    """Drop every cached resource. Used by tests, and after a bulk import."""
    _cache.clear()


SCHEMA_DOC = """\
# Syllogic data model

Hand-written, not generated. It states the things that are true across every
tool and that an agent cannot infer from a response.

## Amounts

- Decimal numbers in **major units** -- euros, not cents. `-12.5` is twelve
  euros fifty, spent.
- Sign convention: negative is money out, positive is money in. `transaction_type`
  (`"debit"` / `"credit"`) says the same thing and is what aggregates filter on.
- Every amount has a `currency` beside it. Never infer one from the account,
  the user or a sibling field.

## Currency

- Each account holds one currency; a user has one **functional currency** that
  totals are reported in.
- Row-level responses carry the native `amount` + `currency`. Where a converted
  figure exists it is named separately (`functional_amount`, `balance`), with
  the functional currency alongside.
- A row that cannot be stated in the functional currency -- no exchange rate on
  record -- is **excluded** from aggregates rather than added unconverted.
  Aggregates report `unconverted_transaction_count` (or `unconverted_count`,
  or an `unconverted` object) to say how many. Non-zero means the total is an
  undercount and should be reported as one.

## Dates

- `YYYY-MM-DD` for dates, RFC-3339 for instants.
- `from_date` and `to_date` are both **inclusive**. `to_date="2026-09-30"`
  covers all of the 30th, up to 23:59:59.

## Categories -- the rule most worth knowing

A transaction carries two category fields:

- `category_id` -- the **user's override**. Set by a person, or by an agent
  through `update_transaction_category`.
- `category_system_id` -- the **AI's assignment**, made at import.

**The effective category is `category_id` when it is set, and
`category_system_id` otherwise.** Every aggregate in this server follows that
rule. Reading only `category_id` undercounts; reading only
`category_system_id` ignores every correction the user has ever made. Both
mistakes produce numbers that look right.

`update_transaction_category` writes `category_id`, so it always wins, and it
never destroys the AI's guess.

## Transfers

Movements between the user's own accounts are not spending. They are excluded
from analytics via `include_in_analytics=false`, except for the
`savings_transfer` and `investment_transfer` system categories, which a budget
may deliberately track.

## Writes

- Every write tool takes `dry_run`. It applies the change, reports it, and
  rolls it back -- so the preview reflects constraints, not guesses.
- Single-entity writes answer with `changed`, `before`, `after` and
  `fields_changed`. `changed: false` means it was already that way; say so
  rather than claiming an edit.
- `create_*` and `update_*` take `idempotency_key`. Reuse it to retry safely;
  the same key with different arguments is rejected.

## Failures

Tools raise rather than returning an error body. There is no `success` field
to check. Error messages carry the way out: the allowed values, the candidate
ids, or the expected format.

## Picking a tool

- Totals by category, optionally per month: `get_amounts_by_category`.
- Rows matching text: `search_transactions` (pass `queries` for several terms
  at once, and `match_mode="word"` for merchant names).
- Rows matching a plain filter, no text: `list_transactions`.
- Tools whose description begins DEPRECATED still work for one release. Use
  what they point at.
"""


def register(mcp) -> None:
    """Attach the resources to a FastMCP server.

    A function rather than decorators at import time, so `server.py` keeps
    one obvious place where everything gets registered.
    """

    @mcp.resource(
        "syllogic://schema",
        name="Syllogic data model",
        description=(
            "Field semantics that hold across every tool: units, currency and "
            "conversion, inclusive dates, and which of the two category fields wins."
        ),
        mime_type="text/markdown",
    )
    def schema() -> str:
        return SCHEMA_DOC

    @mcp.resource(
        "syllogic://accounts",
        name="Accounts",
        description=(
            "Every account: id, name, type, asset class, institution and currency. "
            "Balances are excluded on purpose -- read them with get_account()."
        ),
        mime_type="application/json",
    )
    def accounts_resource() -> str:
        user_id = get_mcp_user_id()

        def build() -> str:
            rows = account_tools.list_accounts(user_id)
            # Anything that moves is dropped. What is left is identity, and
            # identity is what a cached resource can honestly serve.
            keep = ("id", "name", "account_type", "asset_class", "institution", "currency")
            return json.dumps(
                [{k: row.get(k) for k in keep} for row in rows],
                indent=2,
            )

        return _cached("syllogic://accounts", user_id, ACCOUNTS_TTL, build)

    @mcp.resource(
        "syllogic://categories",
        name="Categories",
        description=(
            "The category tree, with each category's description and "
            "categorization_instructions -- the rules the user has taught the system."
        ),
        mime_type="application/json",
    )
    def categories_resource() -> str:
        user_id = get_mcp_user_id()

        def build() -> str:
            with get_db() as db:
                return category_tree.serialize_for_prompt(
                    db,
                    user_id,
                    types=category_tree.ALL_CATEGORY_TYPES,
                    leaves_only=False,
                )

        return _cached("syllogic://categories", user_id, CATEGORIES_TTL, build)

    @mcp.resource(
        "syllogic://people",
        name="Household",
        description="The people in the household and their ownership shares.",
        mime_type="application/json",
    )
    def people_resource() -> str:
        user_id = get_mcp_user_id()

        def build() -> str:
            return json.dumps(people_tools.list_people(user_id), indent=2)

        return _cached("syllogic://people", user_id, PEOPLE_TTL, build)
