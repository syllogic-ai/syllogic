from __future__ import annotations

import json
from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest

from app.models import InvestmentPlan, User, Person, Account, AccountOwner
from app.services import investment_plan_runner


def _emit_block(payload: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = "emit_investment_plan_output"
    block.input = payload
    block.id = "toolu_emit"
    return block


def _final_message(blocks):
    msg = MagicMock()
    msg.content = blocks
    msg.stop_reason = "end_turn"
    msg.usage.input_tokens = 1500
    msg.usage.output_tokens = 300
    return msg


def _valid_payload() -> dict:
    return {
        "totalMonthly": 800,
        "currency": "EUR",
        "cashSnapshot": [],
        "recentActivity": [],
        "pinned": [
            {"slotId": "a", "symbol": "VUAA", "allocatedAmount": 400,
             "verdict": "keep", "rationale": "ok", "riskFlags": [], "newsRefs": []}
        ],
        "discretionary": [
            {"slotId": "b", "theme": "clean energy", "allocatedAmount": 400,
             "topPicks": [{"rank": 1, "symbol": "ENPH", "name": "Enphase",
                           "suggestedAmount": 400, "rationale": "growth",
                           "riskFlags": [], "newsRefs": []}]}
        ],
        "monthlyAction": {
            "proposedBuys": [
                {"symbol": "VUAA", "amount": 400, "source": "pinned", "slotId": "a"},
                {"symbol": "ENPH", "amount": 400, "source": "discretionary", "slotId": "b"},
            ],
            "idleCashNudge": None,
            "notes": [],
        },
        "evidence": [],
    }


@pytest.fixture
def seeded_plan(db_session):
    uid = f"u_{uuid4()}"
    user = User(id=uid, email=f"{uid}@example.com", name="T", email_verified=True)
    db_session.add(user)
    db_session.flush()
    self_p = Person(user_id=uid, name="T", kind="self")
    db_session.add(self_p)
    db_session.flush()
    acct = Account(user_id=uid, name="IBKR", account_type="investment", currency="EUR", functional_balance=1000)
    db_session.add(acct)
    db_session.flush()
    db_session.add(AccountOwner(account_id=acct.id, person_id=self_p.id, share=None))
    plan = InvestmentPlan(
        user_id=uid, name="Test plan", total_monthly=800, currency="EUR",
        slots=[
            {"id": "a", "kind": "pinned", "symbol": "VUAA", "amount": 400},
            {"id": "b", "kind": "discretionary", "theme": "clean energy", "amount": 400},
        ],
        cron="0 8 1 * *", timezone="UTC", schedule_human="1st of month 8am UTC",
        recipient_email=None, model="claude-sonnet-4-6",
    )
    db_session.add(plan)
    db_session.commit()
    return plan


def test_runner_persists_succeeded(seeded_plan, db_session):
    payload = _valid_payload()
    final = _final_message([_emit_block(payload)])
    with patch("app.services.investment_plan_runner.call_agent_step", return_value=final):
        run = investment_plan_runner.run_investment_plan(str(seeded_plan.id))
    fresh = db_session.get(type(run), run.id)
    assert fresh.status == "succeeded"
    assert fresh.output["monthlyAction"]["proposedBuys"][0]["symbol"] == "VUAA"
    assert fresh.cost_cents > 0
    # plan_snapshot frozen
    assert fresh.plan_snapshot is not None


def test_runner_retries_on_invalid_output_then_fails(seeded_plan, db_session):
    bad_block = MagicMock()
    bad_block.type = "tool_use"
    bad_block.name = "emit_investment_plan_output"
    bad_block.input = {"nope": True}
    bad_block.id = "toolu_bad"
    final = _final_message([bad_block])
    with patch("app.services.investment_plan_runner.call_agent_step", side_effect=[final, final]):
        run = investment_plan_runner.run_investment_plan(str(seeded_plan.id))
    fresh = db_session.get(type(run), run.id)
    assert fresh.status == "failed"
    assert fresh.error_message


def test_runner_succeeds_after_retry(seeded_plan, db_session):
    bad_block = MagicMock()
    bad_block.type = "tool_use"
    bad_block.name = "emit_investment_plan_output"
    bad_block.input = {"missing": "fields"}
    bad_block.id = "toolu_bad"
    bad_final = _final_message([bad_block])

    good_final = _final_message([_emit_block(_valid_payload())])
    with patch("app.services.investment_plan_runner.call_agent_step", side_effect=[bad_final, good_final]):
        run = investment_plan_runner.run_investment_plan(str(seeded_plan.id))
    fresh = db_session.get(type(run), run.id)
    assert fresh.status == "succeeded"
