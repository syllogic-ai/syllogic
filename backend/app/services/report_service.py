"""Shared business logic for report CRUD, reused by both the REST routes
(backend/app/routes/reports.py) and the MCP tools
(backend/app/mcp/tools/reports.py) so validation/behavior is identical
regardless of caller.
"""
from __future__ import annotations

from datetime import datetime, time as time_cls
from uuid import UUID

import pydantic
from sqlalchemy.orm import Session

from app.models import Account, Report, ReportRun
from app.schemas import ReportCreate, ReportUpdate
from app.services.report_schedule_service import compute_next_run_at
from tasks.report_tasks import send_report_run


class ReportValidationError(Exception):
    """Raised for any field-level or cross-field validation failure."""


class ReportNotFoundError(Exception):
    """Raised when a report_id doesn't exist or isn't owned by user_id."""


_NON_NULLABLE_UPDATE_FIELDS = ("name", "account_ids", "recipient_emails", "frequency", "is_active", "timezone")


def _parse_time(value: str) -> time_cls:
    hh, mm, *rest = value.split(":")
    ss = int(rest[0]) if rest else 0
    return time_cls(int(hh), int(mm), ss)


def _validate_account_ids(account_ids: list[str], user_id: str, db: Session) -> None:
    if not account_ids:
        return
    parsed_ids = []
    for raw_id in account_ids:
        try:
            parsed_ids.append(UUID(raw_id))
        except ValueError:
            raise ReportValidationError("One or more account_ids are invalid or not owned by this user")
    owned_count = (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.id.in_(parsed_ids))
        .count()
    )
    if owned_count != len(set(parsed_ids)):
        raise ReportValidationError("One or more account_ids are invalid or not owned by this user")


def _recompute_next_run(report: Report) -> None:
    report.next_run_at = compute_next_run_at(
        frequency=report.frequency,
        send_time=report.send_time,
        timezone=report.timezone,
        send_day_of_week=report.send_day_of_week,
        send_day_of_month=report.send_day_of_month,
        after=datetime.utcnow(),
    )


def list_reports(db: Session, user_id: str) -> list[Report]:
    return db.query(Report).filter(Report.user_id == user_id).order_by(Report.created_at.desc()).all()


def _get_owned_report(db: Session, user_id: str, report_id: str) -> Report:
    try:
        report_uuid = UUID(report_id)
    except ValueError:
        raise ReportNotFoundError("Report not found")
    report = db.query(Report).filter(Report.id == report_uuid, Report.user_id == user_id).first()
    if not report:
        raise ReportNotFoundError("Report not found")
    return report


def get_report(db: Session, user_id: str, report_id: str) -> Report:
    return _get_owned_report(db, user_id, report_id)


def create_report(db: Session, user_id: str, payload: dict) -> Report:
    try:
        parsed = ReportCreate(**payload)
    except pydantic.ValidationError as e:
        raise ReportValidationError(str(e))

    _validate_account_ids(parsed.account_ids, user_id, db)

    report = Report(
        user_id=user_id,
        name=parsed.name,
        account_ids=parsed.account_ids,
        transaction_mode=parsed.transaction_mode,
        transaction_count=parsed.transaction_count,
        transaction_direction=parsed.transaction_direction,
        frequency=parsed.frequency,
        send_time=_parse_time(parsed.send_time),
        send_day_of_week=parsed.send_day_of_week,
        send_day_of_month=parsed.send_day_of_month,
        timezone=parsed.timezone,
        recipient_emails=parsed.recipient_emails,
        is_active=parsed.is_active,
    )
    _recompute_next_run(report)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def update_report(db: Session, user_id: str, report_id: str, payload: dict) -> Report:
    report = _get_owned_report(db, user_id, report_id)

    try:
        parsed = ReportUpdate(**payload)
    except pydantic.ValidationError as e:
        raise ReportValidationError(str(e))

    data = parsed.model_dump(exclude_unset=True)

    null_fields = [f for f in _NON_NULLABLE_UPDATE_FIELDS if f in data and data[f] is None]
    if null_fields:
        raise ReportValidationError(f"Field(s) cannot be null: {', '.join(null_fields)}")

    if "account_ids" in data and data["account_ids"] is not None:
        _validate_account_ids(data["account_ids"], user_id, db)
    if "send_time" in data and data["send_time"] is not None:
        data["send_time"] = _parse_time(data["send_time"])
    for field, value in data.items():
        setattr(report, field, value)

    if (report.frequency in ("WEEKLY", "BIWEEKLY") and report.send_day_of_week is None) or (
        report.frequency == "MONTHLY" and report.send_day_of_month is None
    ):
        db.rollback()
        raise ReportValidationError("send_day_of_week/send_day_of_month is required for the selected frequency")

    _recompute_next_run(report)
    db.commit()
    db.refresh(report)
    return report


def delete_report(db: Session, user_id: str, report_id: str) -> None:
    report = _get_owned_report(db, user_id, report_id)
    db.delete(report)
    db.commit()


def send_test_report(db: Session, user_id: str, report_id: str) -> ReportRun:
    report = _get_owned_report(db, user_id, report_id)
    run = ReportRun(
        report_id=report.id,
        scheduled_for=None,
        is_test=True,
        status="SCHEDULED",
        recipient_emails=report.recipient_emails,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    send_report_run.delay(str(run.id))
    return run


def list_report_runs(db: Session, user_id: str, report_id: str) -> list[ReportRun]:
    _get_owned_report(db, user_id, report_id)
    return (
        db.query(ReportRun)
        .filter(ReportRun.report_id == UUID(report_id))
        .order_by(ReportRun.created_at.desc())
        .limit(100)
        .all()
    )
