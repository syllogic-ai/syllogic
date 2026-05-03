from unittest.mock import patch, MagicMock
import pytest

from app.routes import routines_internal


def _fake_response(payload: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_schedule"
    block.input = payload
    msg = MagicMock()
    msg.content = [block]
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 50
    return msg


def test_parse_schedule_happy_path():
    payload = {"cron": "0 8 * * 1", "timezone": "Europe/Amsterdam", "human_readable": "Every Monday 8:00 AM (Europe/Amsterdam)"}
    with patch("app.routes.routines_internal._call_anthropic", return_value=_fake_response(payload)):
        out = routines_internal.parse_schedule_text("every Monday 8am Amsterdam")
    assert out["cron"] == "0 8 * * 1"
    assert out["timezone"] == "Europe/Amsterdam"
    assert "Monday" in out["humanReadable"]


def test_parse_schedule_invalid_cron_rejected():
    payload = {"cron": "not a cron", "timezone": "UTC", "human_readable": "?"}
    with patch("app.routes.routines_internal._call_anthropic", return_value=_fake_response(payload)):
        with pytest.raises(ValueError):
            routines_internal.parse_schedule_text("garbage input")
