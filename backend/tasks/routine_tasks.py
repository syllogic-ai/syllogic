"""Celery tasks for the routine scheduler and runner."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from uuid import UUID

from celery import shared_task
from croniter import croniter

from app.database import SessionLocal
from app.models import InvestmentPlan, InvestmentPlanRun, Routine, RoutineRun
from app.services import anthropic_client, internal_http, investment_plan_runner, routine_runner

log = logging.getLogger(__name__)


def _next_fire_after(cron: str, tz_name: str, after_utc: datetime) -> datetime:
    # croniter is timezone-naive; we operate in UTC for v1. A future improvement:
    # use zoneinfo to interpret cron in the routine's tz. For weekly schedules
    # the difference is at most a few hours and acceptable.
    itr = croniter(cron, after_utc.replace(tzinfo=None))
    return itr.get_next(datetime)


@shared_task(name="scheduled.poll_due")
def poll_due() -> dict:
    """Unified poller — scans routines and investment_plans, dispatches due rows."""
    if not anthropic_client.is_configured():
        log.warning("ANTHROPIC_API_KEY not set; skipping poll_due")
        return {"skipped": True}
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        due_routines = (
            db.query(Routine)
            .filter(Routine.enabled.is_(True))
            .filter((Routine.next_run_at.is_(None)) | (Routine.next_run_at <= now))
            .all()
        )
        due_plans = (
            db.query(InvestmentPlan)
            .filter(InvestmentPlan.enabled.is_(True))
            .filter((InvestmentPlan.next_run_at.is_(None)) | (InvestmentPlan.next_run_at <= now))
            .all()
        )
        for r in due_routines:
            r.next_run_at = _next_fire_after(r.cron, r.timezone, now)
        for p in due_plans:
            p.next_run_at = _next_fire_after(p.cron, p.timezone, now)
        db.commit()
        for r in due_routines:
            run_routine.delay(str(r.id))
        for p in due_plans:
            run_investment_plan.delay(str(p.id))
        return {"routines": len(due_routines), "plans": len(due_plans)}
    finally:
        db.close()


@shared_task(name="routines.poll_due_routines")
def poll_due_routines() -> dict:
    """Deprecated: use scheduled.poll_due. Forwards for backward compat."""
    return poll_due()


@shared_task(name="routines.run_routine")
def run_routine(routine_id: str) -> str:
    """Run the agent and POST the structured output to the frontend renderer."""
    run = routine_runner.run_routine(routine_id)
    if run.status == "succeeded" and run.output is not None:
        try:
            url = _frontend_url("/api/internal/digests/render-and-send")
            path = "/api/internal/digests/render-and-send"
            response = internal_http.signed_post(
                url,
                path=path,
                user_id=str(run.user_id),
                json_body={
                    "routineId": str(run.routine_id),
                    "runId": str(run.id),
                    "output": run.output,
                },
            )
            if response.status_code == 200:
                payload = response.json()
                _mark_sent(run.id, payload.get("messageId"))
            else:
                _mark_send_failed(run.id, f"HTTP {response.status_code}: {response.text[:500]}")
        except Exception as exc:
            log.exception("render-and-send call failed")
            _mark_send_failed(run.id, str(exc))
    return run.status


def _frontend_url(path: str) -> str:
    base = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    return f"{base}{path}"


def _mark_sent(run_id, message_id: str | None) -> None:
    db = SessionLocal()
    try:
        run = db.query(RoutineRun).filter(RoutineRun.id == run_id).first()
        if run is None:
            return
        run.status = "sent"
        run.email_message_id = message_id
        db.commit()
    finally:
        db.close()


def _mark_send_failed(run_id, reason: str) -> None:
    db = SessionLocal()
    try:
        run = db.query(RoutineRun).filter(RoutineRun.id == run_id).first()
        if run is None:
            return
        # Keep status='succeeded' (the agent succeeded) but record the send error.
        run.error_message = (run.error_message or "") + f"\nsend: {reason}"
        db.commit()
    finally:
        db.close()


@shared_task(name="investment_plans.run")
def run_investment_plan(plan_id: str) -> str:
    """Run the agent and POST the structured output to the frontend renderer."""
    run = investment_plan_runner.run_investment_plan(plan_id)
    if run.status == "succeeded" and run.output is not None:
        recipient = (run.plan_snapshot or {}).get("recipientEmail")
        if not recipient:
            db = SessionLocal()
            try:
                plan = db.query(InvestmentPlan).filter(InvestmentPlan.id == run.plan_id).first()
                recipient = plan.recipient_email if plan else None
            finally:
                db.close()
        if recipient:
            try:
                url = _frontend_url("/api/internal/digests/render-and-send-plan")
                path = "/api/internal/digests/render-and-send-plan"
                response = internal_http.signed_post(
                    url, path=path, user_id=str(run.user_id),
                    json_body={"planId": str(run.plan_id), "runId": str(run.id),
                               "recipientEmail": recipient, "output": run.output},
                )
                if response.status_code == 200:
                    payload = response.json()
                    _mark_sent_plan(run.id, payload.get("messageId"))
                else:
                    _mark_send_failed_plan(run.id, f"HTTP {response.status_code}: {response.text[:500]}")
            except Exception as exc:
                log.exception("plan render-and-send failed")
                _mark_send_failed_plan(run.id, str(exc))
    return run.status


def _mark_sent_plan(run_id, message_id: str | None) -> None:
    db = SessionLocal()
    try:
        run = db.query(InvestmentPlanRun).filter(InvestmentPlanRun.id == run_id).first()
        if run is None:
            return
        run.status = "sent"
        run.email_message_id = message_id
        db.commit()
    finally:
        db.close()


def _mark_send_failed_plan(run_id, reason: str) -> None:
    db = SessionLocal()
    try:
        run = db.query(InvestmentPlanRun).filter(InvestmentPlanRun.id == run_id).first()
        if run is None:
            return
        run.error_message = (run.error_message or "") + f"\nsend: {reason}"
        db.commit()
    finally:
        db.close()
