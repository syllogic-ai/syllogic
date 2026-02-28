"""
Server-Sent Events (SSE) endpoints for real-time notifications.
Provides streaming updates for long-running operations like CSV imports.
"""
import asyncio
import json
import os
import logging
from typing import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.db_helpers import get_user_id

logger = logging.getLogger(__name__)

router = APIRouter()


async def import_status_generator(user_id: str, import_id: str) -> AsyncGenerator[str, None]:
    """
    Async generator that streams import status events from Redis Pub/Sub.

    Args:
        user_id: The user ID
        import_id: The CSV import ID

    Yields:
        SSE-formatted event strings
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_client = await aioredis.from_url(redis_url, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel = f"csv_import:{user_id}:{import_id}"
    state_key = f"csv_import_state:{user_id}:{import_id}"

    try:
        await pubsub.subscribe(channel)
        logger.info(f"SSE client subscribed to channel: {channel}")

        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'channel': channel})}\n\n"

        # Check for any stored events (for late subscribers)
        stored_events = await redis_client.hgetall(state_key)
        if stored_events:
            logger.info(f"Sending {len(stored_events)} stored events to late subscriber")
            # Send stored events in order
            event_order = [
                "import_started", "import_progress", "import_completed",
                "subscriptions_started", "subscriptions_completed", "import_failed"
            ]
            for event_type in event_order:
                if event_type in stored_events:
                    data = stored_events[event_type]
                    yield f"event: {event_type}\ndata: {data}\n\n"
                    # If terminal event, close connection
                    if event_type in ("subscriptions_completed", "import_failed"):
                        logger.info(f"Stored terminal event sent, closing SSE: {event_type}")
                        return

        # Keep-alive counter for periodic heartbeats
        heartbeat_interval = 15  # seconds
        last_heartbeat = asyncio.get_event_loop().time()

        while True:
            try:
                # Use asyncio.wait_for to implement timeout for heartbeats
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=1.0
                )

                if message and message["type"] == "message":
                    data = message["data"]
                    try:
                        event_data = json.loads(data)
                        event_type = event_data.get("type", "message")
                        yield f"event: {event_type}\ndata: {data}\n\n"

                        # Close connection on terminal events
                        # - subscriptions_completed: full flow complete (import + subscriptions)
                        # - import_failed: import failed, no subscriptions will run
                        if event_type in ("subscriptions_completed", "import_failed"):
                            logger.info(f"Terminal event received, closing SSE: {event_type}")
                            break
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in message: {data}")
                        yield f"event: message\ndata: {data}\n\n"

            except asyncio.TimeoutError:
                # No message received, check if heartbeat is needed
                current_time = asyncio.get_event_loop().time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    yield f"event: heartbeat\ndata: {json.dumps({'timestamp': current_time})}\n\n"
                    last_heartbeat = current_time

    except asyncio.CancelledError:
        logger.info(f"SSE connection cancelled for channel: {channel}")
        raise
    except Exception as e:
        logger.error(f"SSE error for channel {channel}: {e}")
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis_client.close()
        logger.info(f"SSE connection closed for channel: {channel}")


def get_cors_origin() -> str:
    """Get allowed CORS origin from environment."""
    return os.getenv("FRONTEND_URL") or os.getenv("APP_URL", "http://localhost:3000")


@router.get("/import-status/{import_id}")
async def stream_import_status(import_id: str, request: Request):
    """
    Stream import status updates via Server-Sent Events.

    This endpoint establishes an SSE connection that receives real-time
    updates about a CSV import operation. Events include:

    - connected: Initial connection confirmation
    - import_started: Import processing has begun
    - import_progress: Progress update with percentage
    - import_completed: Import finished successfully
    - import_failed: Import failed with error message
    - subscriptions_started: Subscription detection has begun
    - subscriptions_completed: Subscription detection finished
    - heartbeat: Keep-alive ping (every 15 seconds)

    The connection automatically closes after receiving subscriptions_completed
    or import_failed events.

    Args:
        import_id: The CSV import ID

    Returns:
        StreamingResponse with SSE content type
    """
    resolved_user_id = get_user_id()

    # Use configured frontend URL for CORS instead of wildcard
    cors_origin = get_cors_origin()

    return StreamingResponse(
        import_status_generator(resolved_user_id, import_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Access-Control-Allow-Origin": cors_origin,
            "Access-Control-Allow-Credentials": "true",
        }
    )
