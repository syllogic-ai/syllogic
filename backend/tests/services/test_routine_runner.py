from __future__ import annotations

import json
from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest

from app.models import Routine, RoutineRun, User, Person, Account, AccountOwner
from app.services import routine_runner


def _emit_block(payload: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_routine_output"
    block.input = payload
    block.id = "toolu_emit"
    return block


def _final_message(blocks):
    msg = MagicMock()
    msg.content = blocks
    msg.stop_reason = "end_turn"
    msg.usage.input_tokens = 1000
    msg.usage.output_tokens = 200
    return msg


def _green_payload(person_id: str) -> dict:
    return {
        "status": "GREEN",
        "confidence": "high",
        "headline": "Stay the course",
        "summary": "All on track.",
        "evidence": [],
        "household": {"people": [{
            "personId": person_id, "name": "You",
            "cash": 1000, "investments": 0, "properties": 0, "vehicles": 0, "total": 1000,
        }]},
        "positions": [],
        "news": [],
        "recommendations": [],
    }


@pytest.fixture
def seeded_routine(db_session):
    """Minimal user + person + account + routine for the runner test."""
    uid = f"u_{uuid4()}"
    user = User(id=uid, email=f"{uid}@example.com", name="Test", email_verified=True)
    db_session.add(user)
    db_session.flush()
    self_p = Person(user_id=uid, name="Test", kind="self")
    db_session.add(self_p)
    db_session.flush()
    acct = Account(user_id=uid, name="Bank", account_type="checking", currency="EUR", functional_balance=1000)
    db_session.add(acct)
    db_session.flush()
    db_session.add(AccountOwner(account_id=acct.id, person_id=self_p.id, share=None))
    routine = Routine(
        user_id=uid, name="Test routine", prompt="Test prompt",
        cron="0 8 * * 1", timezone="UTC", schedule_human="Mon 8am UTC",
        recipient_email="test@example.com", model="claude-sonnet-4-6",
    )
    db_session.add(routine)
    db_session.commit()
    return routine, str(self_p.id)


def test_runner_persists_succeeded_run(seeded_routine, db_session):
    routine, person_id = seeded_routine
    payload = _green_payload(person_id)
    final = _final_message([_emit_block(payload)])
    with patch("app.services.routine_runner._call_agent_step", return_value=final):
        run = routine_runner.run_routine(str(routine.id))
    # run comes from a separate closed session — fetch it fresh via the test session
    fresh_run = db_session.get(RoutineRun, run.id)
    assert fresh_run.status == "succeeded"
    assert fresh_run.output["status"] == "GREEN"
    assert fresh_run.cost_cents is not None and fresh_run.cost_cents > 0


def test_runner_downgrades_amber_without_enough_evidence(seeded_routine, db_session):
    routine, person_id = seeded_routine
    bad = _green_payload(person_id)
    bad["status"] = "AMBER"
    bad["evidence"] = [{"source": "X", "url": "https://x.example", "quote": "q", "relevance": "r"}]
    final = _final_message([_emit_block(bad)])
    # Two calls return the same AMBER-with-1-evidence; runner should downgrade.
    with patch("app.services.routine_runner._call_agent_step", side_effect=[final, final]):
        run = routine_runner.run_routine(str(routine.id))
    fresh_run = db_session.get(RoutineRun, run.id)
    assert fresh_run.status == "succeeded"
    assert fresh_run.output["status"] == "GREEN"
    assert fresh_run.output["flags"]["evidence_threshold_unmet"] is True


def test_runner_records_failure_on_invalid_output(seeded_routine, db_session):
    routine, _ = seeded_routine
    bad_block = MagicMock()
    bad_block.type = "tool_use"
    bad_block.name = "emit_routine_output"
    bad_block.input = {"nope": True}  # missing required fields
    bad_block.id = "toolu_bad"
    final = _final_message([bad_block])
    # Two calls, both invalid → run fails.
    with patch("app.services.routine_runner._call_agent_step", side_effect=[final, final]):
        run = routine_runner.run_routine(str(routine.id))
    fresh_run = db_session.get(RoutineRun, run.id)
    assert fresh_run.status == "failed"
    assert fresh_run.error_message
