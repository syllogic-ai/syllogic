"""Celery tasks for demo environment maintenance."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Optional

from celery_app import celery_app
from app.database import SessionLocal
from app.services.demo_seed_service import DEMO_DEFAULT_START_DATE, DemoSeedService

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@celery_app.task(bind=True, max_retries=2, name="tasks.demo_tasks.reset_demo_environment")
def reset_demo_environment(
    self,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
) -> dict:
    """Nightly reset task for shared demo data."""
    if not _env_bool("DEMO_MODE", default=False):
        logger.info("[DEMO_RESET] Skipped: DEMO_MODE is disabled")
        return {"skipped": True, "reason": "DEMO_MODE_DISABLED"}

    if not _env_bool("DEMO_RESET_ENABLED", default=False):
        logger.info("[DEMO_RESET] Skipped: DEMO_RESET_ENABLED is disabled")
        return {"skipped": True, "reason": "DEMO_RESET_DISABLED"}

    resolved_user_id = user_id or os.getenv("DEMO_SHARED_USER_ID")
    resolved_user_email = user_email or os.getenv("DEMO_SHARED_USER_EMAIL")

    if not resolved_user_id and not resolved_user_email:
        logger.error("[DEMO_RESET] Missing demo user identity (DEMO_SHARED_USER_ID / DEMO_SHARED_USER_EMAIL)")
        return {
            "skipped": True,
            "reason": "MISSING_DEMO_USER_IDENTITY",
        }

    random_seed = int(os.getenv("DEMO_SEED_RANDOM_SEED", "42"))
    session = SessionLocal()
    try:
        service = DemoSeedService(session, random_seed=random_seed)
        user = service.resolve_user(user_id=resolved_user_id, email=resolved_user_email)
        summary = service.seed_for_user(
            user=user,
            start_date=DEMO_DEFAULT_START_DATE,
            end_date=date.today(),
            reset=True,
        )

        logger.info(
            "[DEMO_RESET] Completed reset for user=%s transactions=%s accounts=%s categories=%s",
            summary.get("user_id"),
            summary.get("transactions_created"),
            summary.get("accounts_created"),
            summary.get("categories_created"),
        )
        return summary
    except Exception as exc:  # noqa: BLE001
        logger.exception("[DEMO_RESET] Failed demo reset: %s", exc)
        raise
    finally:
        session.close()


@celery_app.task(bind=True, max_retries=2, name="tasks.demo_tasks.append_previous_day_demo_transactions")
def append_previous_day_demo_transactions(
    self,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
) -> dict:
    """Append previous-day demo transactions to keep timeline current."""
    if not _env_bool("DEMO_MODE", default=False):
        logger.info("[DEMO_DAILY] Skipped: DEMO_MODE is disabled")
        return {"skipped": True, "reason": "DEMO_MODE_DISABLED"}

    if not _env_bool("DEMO_DAILY_ENGINE_ENABLED", default=False):
        logger.info("[DEMO_DAILY] Skipped: DEMO_DAILY_ENGINE_ENABLED is disabled")
        return {"skipped": True, "reason": "DEMO_DAILY_ENGINE_DISABLED"}

    resolved_user_id = user_id or os.getenv("DEMO_SHARED_USER_ID")
    resolved_user_email = user_email or os.getenv("DEMO_SHARED_USER_EMAIL")

    if not resolved_user_id and not resolved_user_email:
        logger.error("[DEMO_DAILY] Missing demo user identity (DEMO_SHARED_USER_ID / DEMO_SHARED_USER_EMAIL)")
        return {
            "skipped": True,
            "reason": "MISSING_DEMO_USER_IDENTITY",
        }

    random_seed = int(os.getenv("DEMO_SEED_RANDOM_SEED", "42"))
    coverage_end = date.today()
    target_date = date.today() - timedelta(days=1)

    session = SessionLocal()
    try:
        service = DemoSeedService(session, random_seed=random_seed)
        user = service.resolve_user(user_id=resolved_user_id, email=resolved_user_email)
        coverage_summary = service.ensure_demo_coverage(
            user=user,
            start_date=DEMO_DEFAULT_START_DATE,
            end_date=coverage_end,
        )
        summary = service.append_previous_day_transactions(user=user, target_date=target_date)
        summary["coverage"] = coverage_summary

        logger.info(
            "[DEMO_DAILY] Completed daily append for user=%s target_date=%s created=%s skipped=%s coverage_action=%s",
            user.id,
            summary.get("target_date"),
            summary.get("transactions_created", 0),
            summary.get("skipped", False),
            coverage_summary.get("action"),
        )
        return summary
    except Exception as exc:  # noqa: BLE001
        logger.exception("[DEMO_DAILY] Failed daily append: %s", exc)
        raise
    finally:
        session.close()
