"""
Orchestrates a routine run: agent loop, tool calls, structured output validation,
evidence-threshold downgrade, persistence.

The agent loop here is intentionally minimal — we use Anthropic messages.create
with tool definitions for our MCP tools + web search + a final emit_routine_output
tool. We iterate until the model emits the output tool. This avoids the heavier
Claude Agent SDK runtime while keeping the behavior equivalent for our use case.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.database import SessionLocal
from app.mcp.tools import (
    investments as investment_tools,
    people as people_tools,
)
from app.models import Routine, RoutineRun
from app.schemas_routines import RoutineOutput
from app.services import anthropic_client

log = logging.getLogger(__name__)

MAX_AGENT_STEPS = 30
EVIDENCE_THRESHOLD = 3

# Built from the Pydantic schema so the agent sees exactly what we'll validate against.
EMIT_OUTPUT_TOOL = {
    "name": "emit_routine_output",
    "description": "Emit the final structured digest output. Call this exactly once at the end.",
    "input_schema": RoutineOutput.model_json_schema(),
}


def _mcp_tool_defs() -> list[dict]:
    """Anthropic tool definitions for the in-process MCP tools we expose to the agent."""
    return [
        {
            "name": "list_people",
            "description": "List people in the household.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "get_household_summary",
            "description": "Per-person net worth across cash, investments, properties, vehicles.",
            "input_schema": {
                "type": "object",
                "properties": {"person_ids": {"type": "array", "items": {"type": "string"}}},
                "required": [],
            },
        },
        {
            "name": "list_holdings",
            "description": "List investment holdings; pass person_ids to scope to a single person.",
            "input_schema": {
                "type": "object",
                "properties": {"person_ids": {"type": "array", "items": {"type": "string"}}},
                "required": [],
            },
        },
        {
            "name": "get_portfolio_summary",
            "description": "Portfolio summary; pass person_ids to scope.",
            "input_schema": {
                "type": "object",
                "properties": {"person_ids": {"type": "array", "items": {"type": "string"}}},
                "required": [],
            },
        },
        {
            "name": "get_unrealized_pnl",
            "description": "Unrealized P&L; pass person_ids to scope.",
            "input_schema": {
                "type": "object",
                "properties": {"person_ids": {"type": "array", "items": {"type": "string"}}},
                "required": [],
            },
        },
    ]


def _dispatch_mcp(name: str, args: dict, user_id: str) -> Any:
    """Route a tool name to the corresponding in-process MCP tool function."""
    person_ids = args.get("person_ids")
    if name == "list_people":
        return people_tools.list_people(user_id)
    if name == "get_household_summary":
        return people_tools.get_household_summary(user_id, person_ids)
    if name == "list_holdings":
        return investment_tools.list_holdings(user_id, person_ids=person_ids)
    if name == "get_portfolio_summary":
        return investment_tools.get_portfolio_summary(user_id, person_ids=person_ids)
    if name == "get_unrealized_pnl":
        return investment_tools.get_unrealized_pnl(user_id, person_ids=person_ids)
    raise ValueError(f"unknown tool: {name}")


def _call_agent_step(client, model: str, system: str, messages: list[dict], tools: list[dict]):
    """Wrapper so tests can patch a single function instead of mocking the whole SDK.

    The ``client`` argument is accepted for interface consistency but the real
    Anthropic client is obtained here (so tests that patch this function never
    need to supply a live client or a real API key).
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


def _serialize_block(b) -> dict:
    """Convert an Anthropic SDK block into a dict suitable for re-sending in messages."""
    btype = getattr(b, "type", None)
    if btype == "text":
        return {"type": "text", "text": b.text}
    if btype == "tool_use":
        return {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
    return {"type": btype}


def _agent_loop(routine: Routine, transcript: list[dict]) -> tuple[dict | None, Any]:
    """Run the agent loop until emit_routine_output is called or MAX_AGENT_STEPS reached.

    Returns (final_output_dict_or_None, last_message_object_for_usage)."""
    # client=None causes _call_agent_step to obtain the real client lazily,
    # which means test patches on _call_agent_step work without a real API key.
    client = None
    user_id = routine.user_id
    tools = _mcp_tool_defs() + [
        {"type": "web_search_20250305", "name": "web_search"},
        EMIT_OUTPUT_TOOL,
    ]
    system = (
        "You are reviewing the user's household financial strategy.\n"
        "Default verdict is GREEN unless evidence strongly supports change.\n"
        f"AMBER or RED requires at least {EVIDENCE_THRESHOLD} independent high-quality sources.\n"
        "Always finish by calling the emit_routine_output tool exactly once.\n\n"
        f"User prompt:\n{routine.prompt}"
    )
    messages: list[dict] = [
        {"role": "user", "content": "Begin the analysis. Use the tools as needed, then emit the output."}
    ]

    last_message = None
    for step in range(MAX_AGENT_STEPS):
        last_message = _call_agent_step(client, routine.model, system, messages, tools)
        transcript.append({"step": step, "stop_reason": getattr(last_message, "stop_reason", None)})
        assistant_blocks = last_message.content
        messages.append({"role": "assistant", "content": [
            _serialize_block(b) for b in assistant_blocks
        ]})
        tool_results: list[dict] = []
        emitted_payload: dict | None = None
        for b in assistant_blocks:
            if getattr(b, "type", None) != "tool_use":
                continue
            if b.name == "emit_routine_output":
                emitted_payload = b.input
                continue
            if b.name == "web_search":
                # Anthropic-side server tool; nothing to do.
                continue
            try:
                result = _dispatch_mcp(b.name, b.input or {}, user_id)
                content = json.dumps(result, default=str)
            except Exception as exc:
                content = f"ERROR: {exc}"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": b.id,
                "content": content,
            })
        if emitted_payload is not None:
            return emitted_payload, last_message
        if not tool_results:
            messages.append({"role": "user", "content": "Please continue and call emit_routine_output when ready."})
            continue
        messages.append({"role": "user", "content": tool_results})

    return None, last_message


def _validate_or_downgrade(payload: dict) -> tuple[dict, list[str]]:
    """Validate against the Pydantic schema; if AMBER/RED with insufficient evidence, downgrade to GREEN."""
    errors: list[str] = []
    try:
        validated = RoutineOutput.model_validate(payload).model_dump(by_alias=True)
    except ValidationError as exc:
        errors.append(str(exc))
        return payload, errors

    if validated["status"] in ("AMBER", "RED") and len(validated["evidence"]) < EVIDENCE_THRESHOLD:
        validated["status"] = "GREEN"
        validated.setdefault("flags", {})
        validated["flags"]["evidence_threshold_unmet"] = True
    return validated, errors


def run_routine(routine_id: str) -> RoutineRun:
    """Synchronous run; the Celery task wraps this. Returns the persisted RoutineRun row."""
    db = SessionLocal()
    try:
        routine = db.query(Routine).filter(Routine.id == UUID(routine_id)).first()
        if routine is None:
            raise ValueError(f"routine {routine_id} not found")

        run = RoutineRun(
            routine_id=routine.id,
            user_id=routine.user_id,
            status="running",
            prompt_snapshot=routine.prompt,
            model_snapshot=routine.model,
            started_at=datetime.utcnow(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        transcript: list[dict] = []
        try:
            payload, last = _agent_loop(routine, transcript)
            if payload is None:
                run.status = "failed"
                run.error_message = "agent did not emit output within MAX_AGENT_STEPS"
            else:
                validated, errors = _validate_or_downgrade(payload)
                if errors:
                    # Retry once.
                    second_payload, last = _agent_loop(routine, transcript)
                    if second_payload is None:
                        run.status = "failed"
                        run.error_message = f"validation failed and retry produced no output: {errors}"
                    else:
                        validated, errors2 = _validate_or_downgrade(second_payload)
                        if errors2:
                            run.status = "failed"
                            run.error_message = f"validation failed twice: {errors2}"
                        else:
                            run.status = "succeeded"
                            run.output = validated
                else:
                    run.status = "succeeded"
                    run.output = validated

            usage = anthropic_client.TokenUsage(
                input_tokens=int(getattr(last.usage, "input_tokens", 0)),
                output_tokens=int(getattr(last.usage, "output_tokens", 0)),
            )
            run.cost_cents = usage.cost_cents(routine.model)
            run.transcript = transcript
            run.completed_at = datetime.utcnow()
            if run.status == "succeeded":
                routine.last_run_at = run.completed_at
            db.commit()
            db.refresh(run)
            return run
        except Exception as exc:
            log.exception("routine run failed")
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.utcnow()
            run.transcript = transcript
            db.commit()
            db.refresh(run)
            return run
    finally:
        db.close()
