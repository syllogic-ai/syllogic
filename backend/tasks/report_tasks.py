"""Celery tasks for scheduled and ad-hoc report newsletter sends."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

from celery_app import celery_app

from app.database import SessionLocal
from app.integrations.mail_adapter import get_mail_adapter
from app.models import Report, ReportRun
from app.services.report_data_service import build_report_payload
from app.services.report_schedule_service import compute_next_run_at

_RENDER_SCRIPT = Path(__file__).resolve().parent.parent.parent / "frontend" / "emails" / "render-report.ts"


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
                db.flush()

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
    try:
        run = db.query(ReportRun).filter(ReportRun.id == report_run_id).first()
        if run is None:
            return
        run.status = "RUNNING"
        run.started_at = datetime.utcnow()
        db.commit()

        report = db.query(Report).filter(Report.id == run.report_id).first()
        try:
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
        except Exception as exc:  # noqa: BLE001 - must never break the Beat loop
            run.status = "FAILED"
            run.error_message = str(exc)
        finally:
            run.finished_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
