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
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

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

    try:
        await pubsub.subscribe(channel)
        logger.info(f"SSE client subscribed to channel: {channel}")

        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'channel': channel})}\n\n"

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
                        if event_type in ("import_completed", "import_failed"):
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


@router.get("/import-status/{user_id}/{import_id}")
async def stream_import_status(user_id: str, import_id: str):
    """
    Stream import status updates via Server-Sent Events.

    This endpoint establishes an SSE connection that receives real-time
    updates about a CSV import operation. Events include:

    - connected: Initial connection confirmation
    - import_started: Import processing has begun
    - import_progress: Progress update with percentage
    - import_completed: Import finished successfully
    - import_failed: Import failed with error message
    - heartbeat: Keep-alive ping (every 15 seconds)

    The connection automatically closes after receiving import_completed
    or import_failed events.

    Args:
        user_id: The user ID
        import_id: The CSV import ID

    Returns:
        StreamingResponse with SSE content type
    """
    return StreamingResponse(
        import_status_generator(user_id, import_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
            "Access-Control-Allow-Origin": "*",  # Enable CORS for SSE
        }
    )
