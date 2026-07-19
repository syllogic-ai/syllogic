"""Celery tasks for scheduled and ad-hoc report newsletter sends."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

from celery_app import celery_app

from app.database import SessionLocal
from app.integrations.mail_adapter import get_mail_adapter
from app.models import Report, ReportRun
from app.services.report_data_service import build_report_payload
from app.services.report_schedule_service import compute_next_run_at

# In a local checkout, backend/ and frontend/ are siblings, so this resolves
# correctly by default. Inside the celery-worker/celery-beat containers
# (backend/Dockerfile), the frontend render assets + node_modules are baked
# in at /frontend/emails and FRONTEND_EMAILS_DIR is set accordingly in
# docker-compose.yml -- see that file and backend/Dockerfile's frontend-deps
# stage.
_DEFAULT_FRONTEND_EMAILS_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "emails"
_FRONTEND_EMAILS_DIR = Path(os.environ.get("FRONTEND_EMAILS_DIR", str(_DEFAULT_FRONTEND_EMAILS_DIR)))
_RENDER_SCRIPT = _FRONTEND_EMAILS_DIR / "render-report.ts"


@celery_app.task(name="tasks.report_tasks.check_due_reports")
def check_due_reports() -> None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        due_reports = (
            db.query(Report)
            .filter(Report.is_active.is_(True), Report.next_run_at <= now)
            .all()
        )
        for report in due_reports:
            run = (
                db.query(ReportRun)
                .filter(ReportRun.report_id == report.id, ReportRun.status == "SCHEDULED", ReportRun.scheduled_for <= now)
                .order_by(ReportRun.scheduled_for.asc())
                .first()
            )
            if run is None:
                run = ReportRun(
                    report_id=report.id,
                    scheduled_for=report.next_run_at,
                    status="SCHEDULED",
                    recipient_emails=report.recipient_emails,
                )
                db.add(run)

            # Commit the due run BEFORE enqueueing so the worker (which may
            # start executing almost immediately with a warm Celery worker
            # and Redis broker) can always find the row by id. Enqueueing
            # before this commit lands is a data-loss race: the task would
            # query for a run that doesn't exist yet, return early, and the
            # send would be silently lost with no FAILED record.
            db.commit()
            db.refresh(run)

            send_report_run.delay(str(run.id))

            report.next_run_at = compute_next_run_at(
                frequency=report.frequency,
                send_time=report.send_time,
                timezone=report.timezone,
                send_day_of_week=report.send_day_of_week,
                send_day_of_month=report.send_day_of_month,
                after=now,
            )
            db.add(ReportRun(
                report_id=report.id,
                scheduled_for=report.next_run_at,
                status="SCHEDULED",
                recipient_emails=report.recipient_emails,
            ))
            db.commit()
    finally:
        db.close()


@celery_app.task(name="tasks.report_tasks.send_report_run")
def send_report_run(report_run_id: str) -> None:
    db = SessionLocal()
    run = None
    try:
        try:
            run = db.query(ReportRun).filter(ReportRun.id == report_run_id).first()
            if run is None:
                return
            if run.status != "SCHEDULED":
                # Already RUNNING/SUCCEEDED/FAILED — do not re-send. Guards
                # against duplicate Celery deliveries (at-least-once
                # delivery, retried tasks, etc.) causing double sends.
                return
            run.status = "RUNNING"
            run.started_at = datetime.utcnow()
            db.commit()

            report = db.query(Report).filter(Report.id == run.report_id).first()

            payload = build_report_payload(db, report)
            payload["manage_url"] = None

            result = subprocess.run(
                ["npx", "tsx", str(_RENDER_SCRIPT)],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(_RENDER_SCRIPT.parent.parent),
            )
            if result.returncode != 0:
                raise RuntimeError(f"render-report.ts failed: {result.stderr}")
            rendered = json.loads(result.stdout)

            adapter = get_mail_adapter()
            adapter.send(
                to=run.recipient_emails,
                subject=f"{report.name} — {datetime.utcnow().date().isoformat()}",
                html=rendered["html"],
                text=rendered["text"],
            )

            run.status = "SUCCEEDED"
            run.finished_at = datetime.utcnow()
            db.commit()
        except Exception as exc:  # noqa: BLE001 - must never break the Beat loop
            _mark_run_failed(db, run, report_run_id, exc)
    finally:
        db.close()


def _mark_run_failed(db, run, report_run_id: str, exc: Exception) -> None:
    """Best-effort attempt to mark a ReportRun as FAILED after any failure.

    The session/transaction may be in an unusable state (e.g. if the failure
    happened during the initial commit), so we roll back first and, if the
    in-memory `run` object is unusable, re-query it by id on a fresh
    transaction before giving up.
    """
    try:
        db.rollback()
    except Exception:  # noqa: BLE001
        pass

    try:
        if run is None:
            run = db.query(ReportRun).filter(ReportRun.id == report_run_id).first()
        if run is None:
            return
        run.status = "FAILED"
        run.error_message = str(exc)
        run.finished_at = datetime.utcnow()
        db.commit()
    except Exception:  # noqa: BLE001 - never let the failure handler itself raise
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
