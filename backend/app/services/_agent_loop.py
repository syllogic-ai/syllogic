"""
Shared helpers for agent loops that run Claude with MCP tools + web search.
Used by routine_runner and investment_plan_runner.
"""
from __future__ import annotations

from typing import Any

from app.mcp.tools import (
    accounts as account_tools,
    investments as investment_tools,
    people as people_tools,
)
from app.services import anthropic_client


def call_agent_step(client, model: str, system: str, messages: list[dict], tools: list[dict]):
    """Wrapper around Anthropic messages.create so callers can patch one function in tests.

    Pass ``client=None`` to lazy-resolve via ``anthropic_client.get_client()`` — useful so
    tests don't need ANTHROPIC_API_KEY set when the entire function is mocked.
    """
    if client is None:
        client = anthropic_client.get_client()
    return client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        tools=tools,
        messages=messages,
    )


def serialize_block(b) -> dict:
    """Convert an Anthropic SDK content block into a dict suitable for re-sending."""
    btype = getattr(b, "type", None)
    if btype == "text":
        return {"type": "text", "text": b.text}
    if btype == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
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
