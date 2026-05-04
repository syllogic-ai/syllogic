"""
Shared helpers for agent loops that run Claude with MCP tools + web search.
Used by routine_runner and investment_plan_runner.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from anthropic import RateLimitError

from app.mcp.tools import (
    accounts as account_tools,
    investments as investment_tools,
    people as people_tools,
)
from app.services import anthropic_client

log = logging.getLogger(__name__)

# Outer retry on top of the SDK's built-in max_retries. Useful for sustained
# rate-limit pressure on low-tier orgs where the per-minute window is the
# bottleneck — the SDK's exponential backoff (capped at ~8s) doesn't span a
# full 60s window. We sleep for the server-suggested Retry-After (or 60s) and
# try again.
_RATE_LIMIT_OUTER_RETRIES = 3


def call_agent_step(client, model: str, system: str, messages: list[dict], tools: list[dict]):
    """Wrapper around Anthropic messages.create so callers can patch one function in tests.

    Pass ``client=None`` to lazy-resolve via ``anthropic_client.get_client()`` — useful so
    tests don't need ANTHROPIC_API_KEY set when the entire function is mocked.

    Adds an outer retry loop for sustained 429s that exhaust the SDK's built-in retries.
    """
    if client is None:
        client = anthropic_client.get_client()

    last_err: Exception | None = None
    for attempt in range(_RATE_LIMIT_OUTER_RETRIES):
        try:
            return client.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
            )
        except RateLimitError as exc:
            last_err = exc
            # Honor Retry-After if Anthropic provided it; otherwise wait a full
            # 60s window so the next attempt starts in a fresh per-minute bucket.
            retry_after_header = (
                exc.response.headers.get("retry-after") if exc.response is not None else None
            )
            try:
                wait_seconds = float(retry_after_header) if retry_after_header else 60.0
            except (TypeError, ValueError):
                wait_seconds = 60.0
            wait_seconds = max(5.0, min(wait_seconds, 120.0))
            log.warning(
                "Anthropic rate limit hit (attempt %d/%d); sleeping %.1fs before retry",
                attempt + 1,
                _RATE_LIMIT_OUTER_RETRIES,
                wait_seconds,
            )
            time.sleep(wait_seconds)
    # Exhausted outer retries.
    assert last_err is not None
    raise last_err


def serialize_block(b) -> dict:
    """Convert an Anthropic SDK content block into a dict suitable for re-sending.

    The Anthropic SDK returns Pydantic models. For known types we hand-build the
    minimal dict; for everything else (server_tool_use, web_search_tool_result,
    thinking, etc.) we round-trip via model_dump() so the API accepts the block
    when re-sent in messages."""
    btype = getattr(b, "type", None)
    if btype == "text":
        return {"type": "text", "text": b.text}
    if btype == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    # Unknown / server-side block (e.g. server_tool_use, web_search_tool_result):
    # round-trip via Pydantic model_dump so the SDK can re-validate when re-sent.
    if hasattr(b, "model_dump"):
        return b.model_dump(mode="json", exclude_none=True)
    if hasattr(b, "to_dict"):
        return b.to_dict()
    return {"type": btype}


def dispatch_mcp(name: str, args: dict, user_id: str) -> Any:
    """Route an Anthropic tool name to the corresponding in-process MCP tool function."""
    person_ids = args.get("person_ids")
    if name == "list_people":
        return people_tools.list_people(user_id)
    if name == "get_household_summary":
        return people_tools.get_household_summary(user_id, person_ids)
    if name == "list_accounts":
        return account_tools.list_accounts(
            user_id,
            person_ids=person_ids,
            asset_class=args.get("asset_class"),
        )
    if name == "list_holdings":
        return investment_tools.list_holdings(user_id, person_ids=person_ids)
    if name == "get_portfolio_summary":
        return investment_tools.get_portfolio_summary(user_id, person_ids=person_ids)
    if name == "get_unrealized_pnl":
        return investment_tools.get_unrealized_pnl(user_id, person_ids=person_ids)
    if name == "get_realized_pnl":
        return investment_tools.get_realized_pnl(
            user_id,
            start_date=args.get("from_date"),
            person_ids=person_ids,
        )
    if name == "search_symbol":
        return investment_tools.search_symbol(user_id, args.get("query", ""))
    raise ValueError(f"unknown MCP tool: {name}")
