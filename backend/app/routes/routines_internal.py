"""Internal endpoints called by the frontend over HMAC-signed requests."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from croniter import croniter

from app.db_helpers import authenticate_internal_request_from_headers
from app.services import anthropic_client
from app.schemas_routines import ParseScheduleRequest, ParseScheduleResponse


router = APIRouter(prefix="/internal/routines", tags=["routines-internal"])


def _verify(request: Request) -> str:
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"
    return authenticate_internal_request_from_headers(
        request.method, path, dict(request.headers)
    )


_PARSE_SYSTEM_PROMPT = """\
You translate natural-language schedules into 5-field cron expressions and IANA timezones.

Rules:
- Always emit a 5-field cron (minute hour dom month dow), no seconds.
- If the user names a city or country, map to a single IANA timezone.
- Default timezone to UTC if no zone is mentioned.
- The human_readable string must read naturally and include the timezone, e.g. "Every Monday 8:00 AM (Europe/Amsterdam)".

Examples:
- "every Monday 8am Amsterdam" → cron "0 8 * * 1", timezone "Europe/Amsterdam"
- "first day of each month at 6:30 in NYC" → cron "30 6 1 * *", timezone "America/New_York"
- "weekdays at 5pm" → cron "0 17 * * 1-5", timezone "UTC"

Respond by calling the emit_schedule tool exactly once.
"""


_EMIT_SCHEDULE_TOOL = {
    "name": "emit_schedule",
    "description": "Return the parsed schedule.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cron": {"type": "string"},
            "timezone": {"type": "string"},
            "human_readable": {"type": "string"},
        },
        "required": ["cron", "timezone", "human_readable"],
    },
}


def _call_anthropic(text: str):
    """Indirection so tests can patch this without hitting the network."""
    client = anthropic_client.get_client()
    return client.messages.create(
        model=anthropic_client.DEFAULT_MODEL,
        max_tokens=400,
        system=_PARSE_SYSTEM_PROMPT,
        tools=[_EMIT_SCHEDULE_TOOL],
        tool_choice={"type": "tool", "name": "emit_schedule"},
        messages=[{"role": "user", "content": text}],
    )


def parse_schedule_text(text: str) -> dict[str, str]:
    msg = _call_anthropic(text)
    for block in getattr(msg, "content", []):
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == "emit_schedule":
            payload = block.input
            cron = payload["cron"]
            tz = payload["timezone"]
            human = payload["human_readable"]
            try:
                croniter(cron, datetime.utcnow())
            except Exception as exc:
                raise ValueError(f"model emitted invalid cron {cron!r}: {exc}") from exc
            return {"cron": cron, "timezone": tz, "humanReadable": human}
    raise ValueError("Anthropic response did not include a tool_use block")


@router.post("/parse-schedule", response_model=ParseScheduleResponse)
async def parse_schedule(request: Request, body: ParseScheduleRequest) -> ParseScheduleResponse:
    _verify(request)
    try:
        out = parse_schedule_text(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ParseScheduleResponse(cron=out["cron"], timezone=out["timezone"], humanReadable=out["humanReadable"])
