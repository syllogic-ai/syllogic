from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_helpers import require_admin
from app.logging_config import apply_log_level
from app.services.app_settings import (
    VALID_LOG_LEVELS,
    AppSettingDecryptError,
    AppSettingEncryptionMissing,
    clear_ai_summary_enabled,
    clear_log_level,
    clear_openai_api_key,
    get_ai_summary_enabled_status,
    get_log_level_status,
    get_openai_api_key_status,
    set_ai_summary_enabled,
    set_log_level,
    set_llm_model,
    set_openai_api_key,
)


router = APIRouter()


class LlmSettingsResponse(BaseModel):
    configured: bool
    source: str
    database_configured: bool
    environment_configured: bool
    base_url: str | None = None
    model: str
    provider: str


class UpdateLlmSettingsRequest(BaseModel):
    api_key: str | None = Field(default=None, min_length=1, max_length=500)
    model: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("LLM API key is required.")
        return normalized

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Model is required.")
        return normalized


def _settings_error_response(exc: Exception) -> HTTPException:
    if isinstance(exc, AppSettingEncryptionMissing):
        return HTTPException(
            status_code=500,
            detail="DATA_ENCRYPTION_KEY_CURRENT is required to store LLM API keys in settings.",
        )
    return HTTPException(
        status_code=500,
        detail="Stored LLM API key could not be decrypted.",
    )


@router.get("/llm", response_model=LlmSettingsResponse)
@router.get("/openai", response_model=LlmSettingsResponse, include_in_schema=False)
def get_llm_settings(admin_user_id: str = Depends(require_admin), db: Session = Depends(get_db)):
    try:
        return get_openai_api_key_status(db)
    except (AppSettingDecryptError, AppSettingEncryptionMissing) as exc:
        raise _settings_error_response(exc) from exc


@router.put("/llm", response_model=LlmSettingsResponse)
@router.put("/openai", response_model=LlmSettingsResponse, include_in_schema=False)
def update_llm_settings(
    payload: UpdateLlmSettingsRequest,
    user_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if payload.api_key is None and payload.model is None:
        raise HTTPException(status_code=400, detail="api_key or model is required.")
    try:
        if payload.api_key is not None:
            set_openai_api_key(db, payload.api_key, updated_by_user_id=user_id)
        if payload.model is not None:
            set_llm_model(db, payload.model, updated_by_user_id=user_id)
        return get_openai_api_key_status(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (AppSettingDecryptError, AppSettingEncryptionMissing) as exc:
        raise _settings_error_response(exc) from exc


@router.delete("/llm", response_model=LlmSettingsResponse)
@router.delete("/openai", response_model=LlmSettingsResponse, include_in_schema=False)
def delete_llm_settings(
    user_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    del user_id
    clear_openai_api_key(db)
    try:
        return get_openai_api_key_status(db)
    except (AppSettingDecryptError, AppSettingEncryptionMissing) as exc:
        raise _settings_error_response(exc) from exc


class LogLevelResponse(BaseModel):
    level: str
    source: str


class UpdateLogLevelRequest(BaseModel):
    level: str = Field(..., min_length=1, max_length=20)

    @field_validator("level")
    @classmethod
    def normalize_level(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in VALID_LOG_LEVELS:
            raise ValueError(f"level must be one of {sorted(VALID_LOG_LEVELS)}.")
        return normalized


@router.get("/log-level", response_model=LogLevelResponse)
def get_log_level(admin_user_id: str = Depends(require_admin), db: Session = Depends(get_db)):
    return get_log_level_status(db)


@router.put("/log-level", response_model=LogLevelResponse)
def update_log_level(
    payload: UpdateLogLevelRequest,
    user_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    status = set_log_level(db, payload.level, updated_by_user_id=user_id)
    apply_log_level(status["level"])
    return status


@router.delete("/log-level", response_model=LogLevelResponse)
def delete_log_level(admin_user_id: str = Depends(require_admin), db: Session = Depends(get_db)):
    status = clear_log_level(db)
    apply_log_level(status["level"])
    return status


class AiSummaryEnabledResponse(BaseModel):
    enabled: bool
    source: str


class UpdateAiSummaryEnabledRequest(BaseModel):
    enabled: bool


@router.get("/ai-summary", response_model=AiSummaryEnabledResponse)
def get_ai_summary_enabled(
    admin_user_id: str = Depends(require_admin), db: Session = Depends(get_db)
):
    return get_ai_summary_enabled_status(db)


@router.put("/ai-summary", response_model=AiSummaryEnabledResponse)
def update_ai_summary_enabled(
    payload: UpdateAiSummaryEnabledRequest,
    user_id: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return set_ai_summary_enabled(db, payload.enabled, updated_by_user_id=user_id)


@router.delete("/ai-summary", response_model=AiSummaryEnabledResponse)
def delete_ai_summary_enabled(
    admin_user_id: str = Depends(require_admin), db: Session = Depends(get_db)
):
    return clear_ai_summary_enabled(db)
