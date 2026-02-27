"""
Redis Pub/Sub event publisher for real-time import status updates.
Publishes events that are consumed by SSE endpoints for client notifications.
"""
import json
import os
import logging
from datetime import datetime
from typing import Optional

import redis

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Publishes import status events to Redis Pub/Sub channels.

    Channel format: csv_import:{user_id}:{import_id}

    Event types:
    - import_started: Import has begun processing
    - import_progress: Progress update after each batch
    - import_completed: Import finished successfully
    - import_failed: Import failed with error
    """

    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize the event publisher.

        Args:
            redis_url: Redis connection URL. If not provided, uses REDIS_URL env var.
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._redis: Optional[redis.Redis] = None

    @property
    def redis(self) -> redis.Redis:
        """Lazy-load Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def _channel(self, user_id: str, import_id: str) -> str:
        """Generate the Redis channel name for an import."""
        return f"csv_import:{user_id}:{import_id}"

    def _state_key(self, user_id: str, import_id: str) -> str:
        """Generate the Redis key for storing import state."""
        return f"csv_import_state:{user_id}:{import_id}"

    def _publish(self, user_id: str, import_id: str, event_data: dict) -> None:
        """
        Publish an event to the import channel and store it for late subscribers.

        Args:
            user_id: The user ID
            import_id: The CSV import ID
            event_data: The event payload to publish
        """
        try:
            channel = self._channel(user_id, import_id)
            state_key = self._state_key(user_id, import_id)
            message = json.dumps(event_data)

            # Publish to channel for active subscribers
            self.redis.publish(channel, message)

            # Store the event for late subscribers (TTL: 5 minutes)
            event_type = event_data.get("type", "")
            pipe = self.redis.pipeline()
            pipe.hset(state_key, event_type, message)
            pipe.expire(state_key, 300)  # 5 minute TTL
            pipe.execute()

            logger.debug(f"Published event to {channel}: {event_type}")
        except Exception as e:
            logger.error(f"Failed to publish event: {e}")

    def publish_import_started(
        self,
        user_id: str,
        import_id: str,
        total_rows: int
    ) -> None:
        """
        Publish an import_started event.

        Args:
            user_id: The user ID
            import_id: The CSV import ID
            total_rows: Total number of transactions to import
        """
        self._publish(user_id, import_id, {
            "type": "import_started",
            "import_id": import_id,
            "total_rows": total_rows,
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.info(f"Import started: {import_id} with {total_rows} rows")

    def publish_import_progress(
        self,
        user_id: str,
        import_id: str,
        processed_rows: int,
        total_rows: int
    ) -> None:
        """
        Publish an import_progress event.

        Args:
            user_id: The user ID
            import_id: The CSV import ID
            processed_rows: Number of rows processed so far
            total_rows: Total number of rows to process
        """
        percentage = int((processed_rows / total_rows) * 100) if total_rows > 0 else 0
        self._publish(user_id, import_id, {
            "type": "import_progress",
            "import_id": import_id,
            "processed_rows": processed_rows,
            "total_rows": total_rows,
            "percentage": percentage,
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.debug(f"Import progress: {import_id} - {processed_rows}/{total_rows} ({percentage}%)")

    def publish_import_completed(
        self,
        user_id: str,
        import_id: str,
        imported_count: int,
        skipped_count: int,
        categorization_summary: Optional[dict] = None
    ) -> None:
        """
        Publish an import_completed event.

        Args:
            user_id: The user ID
            import_id: The CSV import ID
            imported_count: Number of transactions successfully imported
            skipped_count: Number of transactions skipped (duplicates)
            categorization_summary: Optional categorization statistics
        """
        self._publish(user_id, import_id, {
            "type": "import_completed",
            "import_id": import_id,
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "categorization_summary": categorization_summary,
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.info(f"Import completed: {import_id} - {imported_count} imported, {skipped_count} skipped")

    def publish_import_failed(
        self,
        user_id: str,
        import_id: str,
        error: str
    ) -> None:
        """
        Publish an import_failed event.

        Args:
            user_id: The user ID
            import_id: The CSV import ID
            error: Error message describing the failure
        """
        self._publish(user_id, import_id, {
            "type": "import_failed",
            "import_id": import_id,
            "error": error,
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.error(f"Import failed: {import_id} - {error}")

    def publish_subscriptions_started(
        self,
        user_id: str,
        import_id: str
    ) -> None:
        """
        Publish a subscriptions_started event.

        Args:
            user_id: The user ID
            import_id: The CSV import ID
        """
        self._publish(user_id, import_id, {
            "type": "subscriptions_started",
            "import_id": import_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.info(f"Subscription processing started for import: {import_id}")

    def publish_subscriptions_completed(
        self,
        user_id: str,
        import_id: str,
        matched_count: int,
        detected_count: int
    ) -> None:
        """
        Publish a subscriptions_completed event.

        Args:
            user_id: The user ID
            import_id: The CSV import ID
            matched_count: Number of transactions matched to existing subscriptions
            detected_count: Number of new subscriptions detected
        """
        self._publish(user_id, import_id, {
            "type": "subscriptions_completed",
            "import_id": import_id,
            "matched_count": matched_count,
            "detected_count": detected_count,
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.info(
            f"Subscription processing completed for import: {import_id} - "
            f"{matched_count} matched, {detected_count} detected"
        )

    def close(self) -> None:
        """Close the Redis connection."""
        if self._redis:
            self._redis.close()
            self._redis = None
