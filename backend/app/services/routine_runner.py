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
from app.models import Routine, RoutineRun
from app.schemas_routines import RoutineOutput
from app.services import anthropic_client
from app.services._agent_loop import call_agent_step, dispatch_mcp, serialize_block

log = logging.getLogger(__name__)

MAX_AGENT_STEPS = 15  # Tighter cap — each web_search-using step grows input by 5-20k tokens
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



def _agent_loop(routine: Routine, transcript: list[dict], usage_totals: dict) -> tuple[dict | None, Any]:
    """Run the agent loop until emit_routine_output is called or MAX_AGENT_STEPS reached.

    Returns (final_output_dict_or_None, last_message_object).
    Accumulates token counts into usage_totals["input"] and usage_totals["output"]."""
    # client=None causes call_agent_step to obtain the real client lazily,
    # which means test patches on call_agent_step work without a real API key.
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
        last_message = call_agent_step(client, routine.model, system, messages, tools)
        usage_totals["input"] += int(getattr(last_message.usage, "input_tokens", 0))
        usage_totals["output"] += int(getattr(last_message.usage, "output_tokens", 0))
        transcript.append({"step": step, "stop_reason": getattr(last_message, "stop_reason", None)})
        assistant_blocks = last_message.content
        messages.append({"role": "assistant", "content": [
            serialize_block(b) for b in assistant_blocks
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
                result = dispatch_mcp(b.name, b.input or {}, user_id)
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


def _normalize_payload(payload: dict) -> dict:
    """Heal common Anthropic tool-input quirks.

    Sonnet sometimes serializes nested object/array values as JSON-encoded strings
    when the tool's input_schema has deeply nested types. We pre-walk the payload
    and json.loads any string that looks like a JSON object or array. Idempotent.
    """
    if not isinstance(payload, dict):
        return payload
    healed: dict = {}
    for k, v in payload.items():
        if isinstance(v, str) and v and v[0] in ("{", "["):
            try:
                healed[k] = json.loads(v)
                continue
            except json.JSONDecodeError:
                pass
        healed[k] = v
    return healed


def _validate_or_downgrade(payload: dict) -> tuple[dict, list[str]]:
    """Validate against the Pydantic schema; if AMBER/RED with insufficient evidence, downgrade to GREEN."""
    payload = _normalize_payload(payload)
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
        usage_totals: dict = {"input": 0, "output": 0}
        try:
            payload, last = _agent_loop(routine, transcript, usage_totals)
            if payload is None:
                run.status = "failed"
                run.error_message = "agent did not emit output within MAX_AGENT_STEPS"
            else:
                validated, errors = _validate_or_downgrade(payload)
                if errors:
                    # Retry once.
                    second_payload, last = _agent_loop(routine, transcript, usage_totals)
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
                input_tokens=usage_totals["input"],
                output_tokens=usage_totals["output"],
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
