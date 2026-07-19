from datetime import datetime, time as time_cls
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_helpers import get_user_id
from app.models import Account, Report, ReportRun
from app.schemas import ReportCreate, ReportResponse, ReportRunResponse, ReportUpdate
from app.services.report_schedule_service import compute_next_run_at
from tasks.report_tasks import send_report_run

router = APIRouter()


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
            raise HTTPException(
                status_code=422,
                detail="One or more account_ids are invalid or not owned by this user",
            )
    owned_count = (
        db.query(Account)
        .filter(Account.user_id == user_id, Account.id.in_(parsed_ids))
        .count()
    )
    if owned_count != len(set(parsed_ids)):
        raise HTTPException(
            status_code=422,
            detail="One or more account_ids are invalid or not owned by this user",
        )


def _recompute_next_run(report: Report) -> None:
    report.next_run_at = compute_next_run_at(
        frequency=report.frequency,
        send_time=report.send_time,
        timezone=report.timezone,
        send_day_of_week=report.send_day_of_week,
        send_day_of_month=report.send_day_of_month,
        after=datetime.utcnow(),
    )


@router.post("", response_model=ReportResponse)
def create_report(payload: ReportCreate, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    _validate_account_ids(payload.account_ids, user_id, db)
    report = Report(
        user_id=user_id,
        name=payload.name,
        account_ids=payload.account_ids,
        transaction_mode=payload.transaction_mode,
        transaction_count=payload.transaction_count,
        transaction_direction=payload.transaction_direction,
        frequency=payload.frequency,
        send_time=_parse_time(payload.send_time),
        send_day_of_week=payload.send_day_of_week,
        send_day_of_month=payload.send_day_of_month,
        timezone=payload.timezone,
        recipient_emails=payload.recipient_emails,
        is_active=payload.is_active,
    )
    _recompute_next_run(report)
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("", response_model=list[ReportResponse])
def list_reports(user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    return db.query(Report).filter(Report.user_id == user_id).order_by(Report.created_at.desc()).all()


def _get_owned_report(report_id: UUID, user_id: str, db: Session) -> Report:
    report = db.query(Report).filter(Report.id == report_id, Report.user_id == user_id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: UUID, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    return _get_owned_report(report_id, user_id, db)


@router.patch("/{report_id}", response_model=ReportResponse)
def update_report(report_id: UUID, payload: ReportUpdate, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    report = _get_owned_report(report_id, user_id, db)
    data = payload.model_dump(exclude_unset=True)
    if "account_ids" in data and data["account_ids"] is not None:
        _validate_account_ids(data["account_ids"], user_id, db)
    if "send_time" in data and data["send_time"] is not None:
        data["send_time"] = _parse_time(data["send_time"])
    for field, value in data.items():
        setattr(report, field, value)

    if (report.frequency in ("WEEKLY", "BIWEEKLY") and report.send_day_of_week is None) or (
        report.frequency == "MONTHLY" and report.send_day_of_month is None
    ):
        # setattr() above already mutated the in-session ORM object; roll
        # back so no partial state is ever committed.
        db.rollback()
        raise HTTPException(
            status_code=422,
            detail="send_day_of_week/send_day_of_month is required for the selected frequency",
        )

    _recompute_next_run(report)
    db.commit()
    db.refresh(report)
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: UUID, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    report = _get_owned_report(report_id, user_id, db)
    db.delete(report)
    db.commit()


@router.post("/{report_id}/send-test", response_model=ReportRunResponse)
def send_test_report(report_id: UUID, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    report = _get_owned_report(report_id, user_id, db)
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


@router.get("/{report_id}/runs", response_model=list[ReportRunResponse])
def list_report_runs(report_id: UUID, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    _get_owned_report(report_id, user_id, db)
    return (
        db.query(ReportRun)
        .filter(ReportRun.report_id == report_id)
        .order_by(ReportRun.created_at.desc())
        .limit(100)
        .all()
    )
