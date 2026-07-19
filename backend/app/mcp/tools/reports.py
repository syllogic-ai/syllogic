"""Report (scheduled newsletter) tools for the MCP server.

All mutation tools return {"success": bool, ...} dicts rather than
raising, following the established pattern in categories.py/investments.py
— get_db() does not auto-rollback on exception, so every mutation path
here explicitly rolls back on failure before returning an error dict.
"""
from __future__ import annotations

from app.mcp.dependencies import get_db
from app.services import report_service
from app.services.report_service import ReportDispatchError, ReportNotFoundError, ReportValidationError


def _serialize_report(report) -> dict:
    return {
        "id": str(report.id),
        "name": report.name,
        "account_ids": list(report.account_ids or []),
        "transaction_mode": report.transaction_mode,
        "transaction_count": report.transaction_count,
        "transaction_direction": report.transaction_direction,
        "frequency": report.frequency,
        "send_time": report.send_time.isoformat() if report.send_time else None,
        "send_day_of_week": report.send_day_of_week,
        "send_day_of_month": report.send_day_of_month,
        "timezone": report.timezone,
        "recipient_emails": list(report.recipient_emails or []),
        "is_active": report.is_active,
        "next_run_at": report.next_run_at.isoformat() if report.next_run_at else None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
    }


def _serialize_run(run) -> dict:
    return {
        "id": str(run.id),
        "report_id": str(run.report_id),
        "scheduled_for": run.scheduled_for.isoformat() if run.scheduled_for else None,
        "is_test": run.is_test,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "error_message": run.error_message,
        "recipient_emails": list(run.recipient_emails or []),
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def list_reports(user_id: str) -> list[dict]:
    with get_db() as db:
        return [_serialize_report(r) for r in report_service.list_reports(db, user_id)]


def get_report(user_id: str, report_id: str) -> dict | None:
    with get_db() as db:
        try:
            return _serialize_report(report_service.get_report(db, user_id, report_id))
        except ReportNotFoundError:
            return None


def create_report(
    user_id: str,
    name: str,
    frequency: str,
    recipient_emails: list[str],
    account_ids: list[str] | None = None,
    transaction_mode: str = "RECENT",
    transaction_count: int = 10,
    transaction_direction: str = "ALL",
    send_time: str = "08:00:00",
    send_day_of_week: int | None = None,
    send_day_of_month: int | None = None,
    timezone: str = "UTC",
    is_active: bool = True,
) -> dict:
    payload = {
        "name": name,
        "frequency": frequency,
        "recipient_emails": recipient_emails,
        "account_ids": account_ids or [],
        "transaction_mode": transaction_mode,
        "transaction_count": transaction_count,
        "transaction_direction": transaction_direction,
        "send_time": send_time,
        "send_day_of_week": send_day_of_week,
        "send_day_of_month": send_day_of_month,
        "timezone": timezone,
        "is_active": is_active,
    }
    with get_db() as db:
        try:
            report = report_service.create_report(db, user_id, payload)
            return {"success": True, "report": _serialize_report(report)}
        except ReportValidationError as e:
            db.rollback()
            return {"success": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            db.rollback()
            return {"success": False, "error": f"Database error: {str(e)}"}


def update_report(
    user_id: str,
    report_id: str,
    name: str | None = None,
    account_ids: list[str] | None = None,
    transaction_mode: str | None = None,
    transaction_count: int | None = None,
    transaction_direction: str | None = None,
    frequency: str | None = None,
    send_time: str | None = None,
    send_day_of_week: int | None = None,
    send_day_of_month: int | None = None,
    timezone: str | None = None,
    recipient_emails: list[str] | None = None,
    is_active: bool | None = None,
) -> dict:
    # Only include explicitly-provided (non-None) fields, so omission
    # preserves the existing value (PATCH semantics) rather than nulling
    # it out. Fields that are legitimately settable to a falsy-but-valid
    # value (is_active=False) are still passed through explicitly by the
    # caller providing that exact value, not omitted.
    payload = {
        k: v
        for k, v in {
            "name": name,
            "account_ids": account_ids,
            "transaction_mode": transaction_mode,
            "transaction_count": transaction_count,
            "transaction_direction": transaction_direction,
            "frequency": frequency,
            "send_time": send_time,
            "send_day_of_week": send_day_of_week,
            "send_day_of_month": send_day_of_month,
            "timezone": timezone,
            "recipient_emails": recipient_emails,
            "is_active": is_active,
        }.items()
        if v is not None
    }
    with get_db() as db:
        try:
            report = report_service.update_report(db, user_id, report_id, payload)
            return {"success": True, "report": _serialize_report(report)}
        except ReportNotFoundError as e:
            db.rollback()
            return {"success": False, "error": str(e)}
        except ReportValidationError as e:
            db.rollback()
            return {"success": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            db.rollback()
            return {"success": False, "error": f"Database error: {str(e)}"}


def delete_report(user_id: str, report_id: str) -> dict:
    with get_db() as db:
        try:
            report_service.delete_report(db, user_id, report_id)
            return {"success": True, "error": None}
        except ReportNotFoundError as e:
            db.rollback()
            return {"success": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            db.rollback()
            return {"success": False, "error": f"Database error: {str(e)}"}


def send_test_report(user_id: str, report_id: str) -> dict:
    with get_db() as db:
        try:
            run = report_service.send_test_report(db, user_id, report_id)
            return {"success": True, "run": _serialize_run(run)}
        except ReportNotFoundError as e:
            db.rollback()
            return {"success": False, "error": str(e)}
        except ReportDispatchError as e:
            db.rollback()
            return {"success": False, "error": str(e)}
        except Exception as e:  # noqa: BLE001
            db.rollback()
            return {"success": False, "error": f"Database error: {str(e)}"}


def list_report_runs(user_id: str, report_id: str) -> list[dict]:
    with get_db() as db:
        try:
            return [_serialize_run(r) for r in report_service.list_report_runs(db, user_id, report_id)]
        except ReportNotFoundError:
            return []
