from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_helpers import get_user_id
from app.schemas import ReportCreate, ReportResponse, ReportRunResponse, ReportUpdate
from app.services import report_service
from app.services.report_service import ReportDispatchError, ReportNotFoundError, ReportValidationError

router = APIRouter()


@router.post("", response_model=ReportResponse)
def create_report(payload: ReportCreate, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    try:
        return report_service.create_report(db, user_id, payload.model_dump())
    except ReportValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("", response_model=list[ReportResponse])
def list_reports(user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    return report_service.list_reports(db, user_id)


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: str, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    try:
        return report_service.get_report(db, user_id, report_id)
    except ReportNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{report_id}", response_model=ReportResponse)
def update_report(report_id: str, payload: ReportUpdate, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    try:
        return report_service.update_report(db, user_id, report_id, payload.model_dump(exclude_unset=True))
    except ReportNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReportValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: str, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    try:
        report_service.delete_report(db, user_id, report_id)
    except ReportNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{report_id}/send-test", response_model=ReportRunResponse)
def send_test_report(report_id: str, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    try:
        return report_service.send_test_report(db, user_id, report_id)
    except ReportNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReportDispatchError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))


@router.get("/{report_id}/runs", response_model=list[ReportRunResponse])
def list_report_runs(report_id: str, user_id: str = Depends(get_user_id), db: Session = Depends(get_db)):
    try:
        return report_service.list_report_runs(db, user_id, report_id)
    except ReportNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
