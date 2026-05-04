"""
Celery application configuration for scheduled tasks.
"""
import os
from celery import Celery
from celery.schedules import crontab

# Redis URL for broker and backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "finance_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.csv_import_tasks", "tasks.demo_tasks", "tasks.enable_banking_tasks", "tasks.post_import_pipeline", "tasks.investment_tasks", "tasks.routine_tasks"],
    set_as_current=True,
)
# Ensure @shared_task instances bind to this Celery instance instead of any
# transient default app created by other imports. Required for the API service
# to publish tasks via Redis (without this it falls back to amqp://).
celery_app.set_default()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _build_beat_schedule() -> dict:
    schedule = {}
    demo_mode = _env_bool("DEMO_MODE", default=False)
    demo_reset_enabled = _env_bool("DEMO_RESET_ENABLED", default=False)
    demo_daily_enabled = _env_bool("DEMO_DAILY_ENGINE_ENABLED", default=False)

    if demo_mode and demo_reset_enabled:
        try:
            demo_reset_hour_utc = int(os.getenv("DEMO_RESET_HOUR_UTC", "0"))
        except ValueError:
            demo_reset_hour_utc = 0

        # Keep the hour in a safe UTC range.
        demo_reset_hour_utc = max(0, min(23, demo_reset_hour_utc))
        schedule["demo-reset-nightly"] = {
            "task": "tasks.demo_tasks.reset_demo_environment",
            "schedule": crontab(minute=0, hour=demo_reset_hour_utc),
        }

    if demo_mode and demo_daily_enabled:
        try:
            demo_daily_hour_utc = int(os.getenv("DEMO_DAILY_ENGINE_HOUR_UTC", "2"))
        except ValueError:
            demo_daily_hour_utc = 2
        try:
            demo_daily_minute_utc = int(os.getenv("DEMO_DAILY_ENGINE_MINUTE_UTC", "15"))
        except ValueError:
            demo_daily_minute_utc = 15

        demo_daily_hour_utc = max(0, min(23, demo_daily_hour_utc))
        demo_daily_minute_utc = max(0, min(59, demo_daily_minute_utc))

        schedule["demo-daily-previous-day-transactions"] = {
            "task": "tasks.demo_tasks.append_previous_day_demo_transactions",
            "schedule": crontab(minute=demo_daily_minute_utc, hour=demo_daily_hour_utc),
        }

    # Enable Banking sync schedules (always active — tasks are no-ops if no connections exist)
    schedule["sync-all-bank-connections"] = {
        "task": "tasks.enable_banking_tasks.sync_all_bank_connections",
        "schedule": crontab(minute=0, hour="*/6"),
    }
    schedule["check-consent-expiry"] = {
        "task": "tasks.enable_banking_tasks.check_consent_expiry",
        "schedule": crontab(minute=0, hour=9),
    }

    try:
        investment_hour = int(os.getenv("SYLLOGIC_INVESTMENT_SYNC_HOUR_UTC", "2"))
    except ValueError:
        investment_hour = 2
    investment_hour = max(0, min(23, investment_hour))
    schedule["daily-investment-sync-all"] = {
        "task": "tasks.investment_tasks.daily_investment_sync_all",
        "schedule": crontab(minute=0, hour=investment_hour),
    }

    schedule["scheduled-poll-due"] = {
        "task": "scheduled.poll_due",
        "schedule": 60.0,  # every 60 seconds
    }

    return schedule

# Celery configuration
celery_app.conf.update(
    # Task result settings
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task settings
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # Soft limit at 55 minutes

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_concurrency=4,

    # Beat schedule for periodic tasks
    beat_schedule=_build_beat_schedule(),
)

# Optional: Auto-discover tasks in app
celery_app.autodiscover_tasks(["tasks"])


if __name__ == "__main__":
    celery_app.start()
