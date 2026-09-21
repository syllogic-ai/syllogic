import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.db_helpers import get_request_user_id
from app.rate_limit import is_rate_limited
from app.services.app_settings import get_ai_summary_enabled_status
from app.services.llm_client import create_llm_clients, is_fallback_worthy_error


router = APIRouter()
logger = logging.getLogger(__name__)

# These endpoints proxy to a paid LLM API and take their inputs straight from
# the request body rather than looking anything up, so the only thing
# stopping a signed-in user from burning through the deployment's LLM
# spend is this limit.
_LLM_RATE_LIMIT_MAX = 20
_LLM_RATE_LIMIT_WINDOW_SECONDS = 60


def _enforce_llm_rate_limit() -> None:
    identity = get_request_user_id() or "anonymous"
    if is_rate_limited(f"llm:{identity}", _LLM_RATE_LIMIT_MAX, _LLM_RATE_LIMIT_WINDOW_SECONDS):
        raise HTTPException(status_code=429, detail="Too many AI requests. Please try again later.")


class ColumnMappingRequest(BaseModel):
    headers: list[str] = Field(..., min_length=1, max_length=200)
    sample_rows: list[list[str]] = Field(default_factory=list, max_length=3)
    date_formats: list[str] = Field(..., min_length=1, max_length=50)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, headers: list[str]) -> list[str]:
        if any(len(header) > 500 for header in headers):
            raise ValueError("CSV headers must be at most 500 characters each.")
        return headers

    @field_validator("sample_rows")
    @classmethod
    def validate_sample_rows(cls, rows: list[list[str]]) -> list[list[str]]:
        if any(len(cell) > 2_000 for row in rows for cell in row):
            raise ValueError("CSV samples must be at most 2,000 characters per cell.")
        return rows


class ColumnMappingResponse(BaseModel):
    mapping: dict


@router.post("/column-mapping", response_model=ColumnMappingResponse)
def map_csv_columns(payload: ColumnMappingRequest, db: Session = Depends(get_db)):
    _enforce_llm_rate_limit()
    providers = create_llm_clients(db)
    if not providers:
        raise HTTPException(status_code=503, detail="LLM API is not configured.")

    sample_data = []
    for row in payload.sample_rows[:3]:
        sample_data.append(
            {
                header: (row[index] if index < len(row) else "")
                for index, header in enumerate(payload.headers)
            }
        )

    date_format_options = ", ".join(json.dumps(value) for value in payload.date_formats)
    prompt = f"""You are a CSV column mapping assistant. Analyze these CSV headers and sample data to map them to transaction fields.

Headers: {json.dumps(payload.headers)}

Sample data (first 3 rows):
{json.dumps(sample_data, indent=2)}

Map these columns to the following transaction fields:
- date: The transaction date column (prefer "Completed Date" over "Started Date" if both exist)
- amount: The transaction amount column
- description: The transaction description/narrative column
- merchant: The merchant/payee name column (if separate from description)
- transactionType: The column indicating debit/credit (if exists)
- fee: Column containing transaction fees (if exists)
- state: Column containing transaction state/status (if exists)
- startingBalance: Column containing opening/starting balance (if exists)
- endingBalance: Column containing closing/ending balance (if exists)

Also determine whether amount is signed, its decimal format, credit/debit values,
the exact date format, and the completed state value. Supported date formats:
{date_format_options}

Respond ONLY with a valid JSON object in this exact shape:
{{
  "date": "column_name_or_null",
  "amount": "column_name_or_null",
  "description": "column_name_or_null",
  "merchant": "column_name_or_null",
  "transactionType": "column_name_or_null",
  "fee": "column_name_or_null",
  "state": "column_name_or_null",
  "startingBalance": "column_name_or_null",
  "endingBalance": "column_name_or_null",
  "typeConfig": {{
    "creditValue": "value_that_indicates_credit_or_null",
    "debitValue": "value_that_indicates_debit_or_null",
    "isAmountSigned": true,
    "amountFormat": "AUTO",
    "dateFormat": "one_supported_date_format",
    "completedStateValue": "value_that_indicates_completed_or_null"
  }}
}}

Use null for columns that do not exist or cannot be determined. amountFormat must
be AUTO, DOT_DECIMAL, or COMMA_DECIMAL. Default dateFormat to DD-MM-YYYY when uncertain."""

    last_error: Exception | None = None
    for provider in providers:
        client, model, label = provider.client, provider.model, provider.label
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            content = response.choices[0].message.content or ""
            match = re.search(r"\{[\s\S]*\}", content)
            if not match:
                raise ValueError("LLM response did not contain a JSON object")
            mapping = json.loads(match.group(0))
            if not isinstance(mapping, dict):
                raise ValueError("LLM response was not a JSON object")
            if label != "primary":
                logger.info("LLM column mapping served by '%s' provider (model=%s)", label, model)
            return {"mapping": mapping}
        except Exception as exc:
            last_error = exc
            logger.warning(
                "LLM column mapping via '%s' provider failed: %s: %s",
                label,
                type(exc).__name__,
                exc,
            )
            if is_fallback_worthy_error(exc):
                continue
            # Non-quota/auth error (bad response shape, etc.) — same failure
            # mode would repeat on the fallback provider, so stop here.
            break

    logger.error("LLM column mapping failed on every configured provider", exc_info=last_error)
    raise HTTPException(status_code=502, detail="LLM column mapping failed.") from last_error


def _require_ai_summary_enabled(db: Session) -> None:
    if not get_ai_summary_enabled_status(db)["enabled"]:
        raise HTTPException(status_code=403, detail="AI summaries are disabled.")


def _generate_narrative(prompt: str, db: Session, log_label: str) -> str:
    """Send `prompt` to the configured LLM providers (primary then fallback)
    and return the plain-text narrative response. Shared by the dashboard and
    transactions summary endpoints — same provider-loop/fallback pattern as
    map_csv_columns above, just returning text instead of parsed JSON."""
    providers = create_llm_clients(db)
    if not providers:
        raise HTTPException(status_code=503, detail="LLM API is not configured.")

    last_error: Exception | None = None
    for provider in providers:
        client, model, label = provider.client, provider.model, provider.label
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                raise ValueError("LLM response was empty")
            if label != "primary":
                logger.info("%s served by '%s' provider (model=%s)", log_label, label, model)
            return content
        except Exception as exc:
            last_error = exc
            logger.warning(
                "%s via '%s' provider failed: %s: %s", log_label, label, type(exc).__name__, exc
            )
            if is_fallback_worthy_error(exc):
                continue
            break

    logger.error("%s failed on every configured provider", log_label, exc_info=last_error)
    raise HTTPException(status_code=502, detail=f"{log_label} failed.") from last_error


class DashboardSummaryRequest(BaseModel):
    currency: str = Field(..., min_length=1, max_length=10)
    period_label: str = Field(..., min_length=1, max_length=100)
    balance: float
    period_income: float
    period_spending: float


class TransactionsSummaryRequest(BaseModel):
    currency: str = Field(..., min_length=1, max_length=10)
    date_from: str = Field(..., min_length=1, max_length=40)
    date_to: str = Field(..., min_length=1, max_length=40)
    total_in: float
    total_out: float


class SummaryResponse(BaseModel):
    summary: str


@router.post("/dashboard-summary", response_model=SummaryResponse)
def generate_dashboard_summary(payload: DashboardSummaryRequest, db: Session = Depends(get_db)):
    _enforce_llm_rate_limit()
    _require_ai_summary_enabled(db)
    prompt = f"""You are a personal finance assistant. Write a short (2-3 sentence),
plain-language narrative summary of this user's finances for "{payload.period_label}".
Be direct and factual, do not invent numbers not given below, and do not use markdown.

Total balance: {payload.balance:.2f} {payload.currency}
Income this period: {payload.period_income:.2f} {payload.currency}
Spending this period: {payload.period_spending:.2f} {payload.currency}"""
    summary = _generate_narrative(prompt, db, "Dashboard AI summary")
    return {"summary": summary}


@router.post("/transactions-summary", response_model=SummaryResponse)
def generate_transactions_summary(
    payload: TransactionsSummaryRequest, db: Session = Depends(get_db)
):
    _enforce_llm_rate_limit()
    _require_ai_summary_enabled(db)
    prompt = f"""You are a personal finance assistant. Write a short (2-3 sentence),
plain-language narrative summary of the user's transactions between {payload.date_from}
and {payload.date_to}. Be direct and factual, do not invent numbers not given below,
and do not use markdown.

Money in: {payload.total_in:.2f} {payload.currency}
Money out: {payload.total_out:.2f} {payload.currency}
Net: {(payload.total_in - payload.total_out):.2f} {payload.currency}"""
    summary = _generate_narrative(prompt, db, "Transactions AI summary")
    return {"summary": summary}
