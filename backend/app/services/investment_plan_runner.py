"""
Orchestrates an investment plan run: pre-computed grounding → agent loop with
MCP tools + web search + emit_investment_plan_output → schema validation →
persistence. Mirrors routine_runner but with a different output schema and
no GREEN/AMBER/RED downgrade rule.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.database import SessionLocal
from app.models import InvestmentPlan, InvestmentPlanRun
from app.schemas_routines import InvestmentPlanOutput
from app.services import anthropic_client
from app.services._agent_loop import call_agent_step, serialize_block, dispatch_mcp
from app.services.grounding import collect_grounding

log = logging.getLogger(__name__)

MAX_AGENT_STEPS = 15  # Tighter cap — each web_search-using step grows input by 5-20k tokens

EMIT_OUTPUT_TOOL = {
    "name": "emit_investment_plan_output",
    "description": "Emit the final structured monthly investment plan output. Call exactly once at the end.",
    "input_schema": InvestmentPlanOutput.model_json_schema(),
}


def _mcp_tool_defs() -> list[dict]:
    return [
        {"name": "list_people", "description": "List people in household.",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "list_accounts", "description": "List accounts; pass asset_class='investment' to scope.",
         "input_schema": {"type": "object", "properties": {"asset_class": {"type": "string"}}, "required": []}},
        {"name": "list_holdings", "description": "List holdings.",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "get_portfolio_summary", "description": "Portfolio-level summary.",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "get_unrealized_pnl", "description": "Unrealized P&L for current holdings.",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
        {"name": "get_realized_pnl", "description": "Realized P&L; pass from_date (YYYY-MM-DD) to scope.",
         "input_schema": {"type": "object", "properties": {"from_date": {"type": "string"}}, "required": []}},
        {"name": "search_symbol", "description": "Search for a ticker by name or symbol.",
         "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    ]


def _build_system_prompt(plan: InvestmentPlan, grounding: dict) -> str:
    slot_lines = []
    for s in (plan.slots or []):
        sid = s.get("id", "?")
        kind = s.get("kind")
        amount = s.get("amount", 0)
        if kind == "pinned":
            symbol = s.get("symbol", "?")
            slot_lines.append(f"- pinned slot {sid}: {symbol} for {amount} {plan.currency}")
        elif kind == "discretionary":
            label = s.get("label") or s.get("theme", "?")
            theme = s.get("theme", "")
            slot_lines.append(f"- discretionary slot {sid} ({label}): {amount} {plan.currency} — theme: {theme}")
        else:
            slot_lines.append(f"- (unknown slot kind {kind} id={sid})")
    slot_block = "\n".join(slot_lines)

    grounding_json = json.dumps(grounding, default=str)

    return f"""You are an investment-research assistant. The user has configured a recurring monthly plan.
You are NOT executing trades — your job is to research and recommend.

Plan: total {plan.total_monthly} {plan.currency} per month. Slots:
{slot_block}

Pre-computed grounding (cash + last 30 days of broker activity):
{grounding_json}

Rules:
- For each pinned slot: emit a verdict (keep|reduce|replace|monitor) with rationale, risk flags, and news refs.
- For each discretionary slot: research the theme and emit up to 10 ranked picks; #1 fills the slot's amount.
- Build monthlyAction.proposedBuys from the verdicts (keep → keep symbol, replace → use replacement symbol) and the #1 of each discretionary slot.
- Use the cashSnapshot to write a brief idleCashNudge if there is meaningful idle cash.
- Always finish by calling emit_investment_plan_output exactly once.

User name / household context: not provided here — call list_people if needed.
"""


def _agent_loop(plan: InvestmentPlan, transcript: list[dict], usage_totals: dict) -> tuple[dict | None, Any]:
    grounding = collect_grounding(plan.user_id)
    user_id = plan.user_id
    tools = _mcp_tool_defs() + [
        {"type": "web_search_20250305", "name": "web_search"},
        EMIT_OUTPUT_TOOL,
    ]
    system = _build_system_prompt(plan, grounding)
    messages: list[dict] = [
        {"role": "user", "content": "Run the analysis. Use tools as needed, then emit the output."}
    ]

    last_message = None
    for step in range(MAX_AGENT_STEPS):
        last_message = call_agent_step(None, plan.model, system, messages, tools)
        usage_totals["input"] += int(getattr(last_message.usage, "input_tokens", 0))
        usage_totals["output"] += int(getattr(last_message.usage, "output_tokens", 0))
        transcript.append({"step": step, "stop_reason": getattr(last_message, "stop_reason", None)})
        assistant_blocks = last_message.content
        messages.append({"role": "assistant", "content": [serialize_block(b) for b in assistant_blocks]})
        tool_results: list[dict] = []
        emitted_payload: dict | None = None
        for b in assistant_blocks:
            if getattr(b, "type", None) != "tool_use":
                continue
            if b.name == "emit_investment_plan_output":
                emitted_payload = b.input
                continue
            if b.name == "web_search":
                continue
            try:
                result = dispatch_mcp(b.name, b.input or {}, user_id)
                content = json.dumps(result, default=str)
            except Exception as exc:
                content = f"ERROR: {exc}"
            tool_results.append({"type": "tool_result", "tool_use_id": b.id, "content": content})
        if emitted_payload is not None:
            return emitted_payload, last_message
        if not tool_results:
            messages.append({"role": "user", "content": "Please call emit_investment_plan_output now."})
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


def _validate(payload: dict) -> tuple[dict, list[str]]:
    payload = _normalize_payload(payload)
    try:
        validated = InvestmentPlanOutput.model_validate(payload).model_dump(by_alias=True)
        return validated, []
    except ValidationError as exc:
        return payload, [str(exc)]


def run_investment_plan(plan_id: str) -> InvestmentPlanRun:
    db = SessionLocal()
    try:
        plan = db.query(InvestmentPlan).filter(InvestmentPlan.id == UUID(plan_id)).first()
        if plan is None:
            raise ValueError(f"investment plan {plan_id} not found")

        snapshot = {
            "name": plan.name,
            "totalMonthly": float(plan.total_monthly),
            "currency": plan.currency,
            "slots": plan.slots,
            "cron": plan.cron,
            "timezone": plan.timezone,
            "recipientEmail": plan.recipient_email,
        }
        run = InvestmentPlanRun(
            plan_id=plan.id, user_id=plan.user_id, status="running",
            plan_snapshot=snapshot, model_snapshot=plan.model,
            started_at=datetime.utcnow(),
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        transcript: list[dict] = []
        usage_totals: dict = {"input": 0, "output": 0}
        try:
            payload, last = _agent_loop(plan, transcript, usage_totals)
            if payload is None:
                run.status = "failed"
                run.error_message = "agent did not emit output within MAX_AGENT_STEPS"
            else:
                validated, errors = _validate(payload)
                if errors:
                    second_payload, last = _agent_loop(plan, transcript, usage_totals)
                    if second_payload is None:
                        run.status = "failed"
                        run.error_message = f"validation failed and retry produced no output: {errors}"
                    else:
                        validated, errors2 = _validate(second_payload)
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
            run.cost_cents = usage.cost_cents(plan.model)
            run.transcript = transcript
            run.completed_at = datetime.utcnow()
            if run.status == "succeeded":
                plan.last_run_at = run.completed_at
            db.commit()
            db.refresh(run)
            return run
        except Exception as exc:
            log.exception("investment plan run failed")
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.utcnow()
            run.transcript = transcript
            db.commit()
            db.refresh(run)
            return run
    finally:
        db.close()
