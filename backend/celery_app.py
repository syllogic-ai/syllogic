"""
Celery application configuration for scheduled tasks.
"""
import os
from celery import Celery

# Redis URL for broker and backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "finance_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.csv_import_tasks"],
)

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
    beat_schedule={},
)

# Optional: Auto-discover tasks in app
celery_app.autodiscover_tasks(["tasks"])


if __name__ == "__main__":
    celery_app.start()
