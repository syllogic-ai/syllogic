"""Saved filter-view presets for the accounts screen (mobile MVP).

Stored in Redis (keyed per user) rather than Postgres — this is a small,
low-stakes preference blob, and Redis is already deployed for
Celery/events (see app/services/event_publisher.py). If durability
guarantees ever need to be stronger, move this to a proper table; the
route contract here would stay the same.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Callable, List

import redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.db_helpers import get_user_id

logger = logging.getLogger(__name__)

router = APIRouter()

_redis_client: redis.Redis | None = None

# Generous upper bound on how many accounts/types/currencies a single filter
# can reference — a user cannot plausibly have more accounts than this, and
# it keeps one client from growing the stored blob without bound.
MAX_FILTER_LIST_LENGTH = 200

# Cap on how many saved views a single user may store. Every list/create call
# re-serialises the whole per-user blob, so this also bounds that cost.
MAX_SAVED_VIEWS_PER_USER = 50

# Optimistic-locking retry bound for the WATCH/MULTI/EXEC read-modify-write
# cycle below. Bounded so a hot key fails fast (409) instead of looping
# forever under contention.
MAX_LOCK_RETRIES = 5


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client


def _redis_key(user_id: str) -> str:
    return f"saved_views:{user_id}"


def _corrupt_redis_key(user_id: str) -> str:
    return f"{_redis_key(user_id)}:corrupt"


class SavedViewFilters(BaseModel):
    account_ids: List[str] = Field(default_factory=list, max_length=MAX_FILTER_LIST_LENGTH)
    account_types: List[str] = Field(default_factory=list, max_length=MAX_FILTER_LIST_LENGTH)
    currencies: List[str] = Field(default_factory=list, max_length=MAX_FILTER_LIST_LENGTH)


class SavedViewCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    filters: SavedViewFilters


class SavedView(SavedViewCreate):
    id: str
    created_at: str


def _parse_blob(raw: str | None, user_id: str, client: redis.Redis) -> List[dict]:
    """Parse the raw JSON blob for a user, recovering from corruption.

    On a `JSONDecodeError` the raw value is copied to a side key so it is
    not lost, a warning is logged with the user id, and an empty list is
    returned so the app stays usable. This function never raises on bad
    input and never writes back to the primary key itself — callers decide
    if/when to persist a fresh value.
    """
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "Corrupt saved_views JSON blob for user_id=%s; preserving raw value at %s",
            user_id,
            _corrupt_redis_key(user_id),
        )
        try:
            client.set(_corrupt_redis_key(user_id), raw)
        except Exception:
            logger.exception(
                "Failed to preserve corrupt saved_views blob for user_id=%s", user_id
            )
        return []


def _load(user_id: str) -> List[dict]:
    client = get_redis()
    raw = client.get(_redis_key(user_id))
    return _parse_blob(raw, user_id, client)


def _atomic_mutate(
    user_id: str, mutate_fn: Callable[[List[dict]], List[dict]]
) -> List[dict]:
    """Atomically read-modify-write the saved-views list for a user.

    Uses Redis optimistic locking: WATCH the key, read the current value,
    let `mutate_fn` compute the new value, then commit with MULTI/EXEC. If
    another writer changed the key in between, EXEC raises `WatchError` and
    the whole cycle retries (bounded by MAX_LOCK_RETRIES). `mutate_fn` may
    raise an HTTPException (e.g. 404/409) to abort the operation outright —
    that propagates immediately without being retried.

    Both create_saved_view and delete_saved_view go through this helper so
    the two mutation paths cannot drift.
    """
    client = get_redis()
    key = _redis_key(user_id)
    for _ in range(MAX_LOCK_RETRIES):
        pipe = client.pipeline(transaction=True)
        try:
            pipe.watch(key)
            raw = pipe.get(key)
            current = _parse_blob(raw, user_id, client)
            new_views = mutate_fn(current)
            pipe.multi()
            pipe.set(key, json.dumps(new_views))
            pipe.execute()
            return new_views
        except redis.WatchError:
            continue
        finally:
            pipe.reset()

    raise HTTPException(
        status_code=409,
        detail="Could not save changes due to concurrent updates; please try again.",
    )


@router.get("/", response_model=List[SavedView])
def list_saved_views(user_id: str = Depends(get_user_id)):
    raw_views = _load(user_id)
    valid_views: List[SavedView] = []
    for entry in raw_views:
        try:
            valid_views.append(SavedView.model_validate(entry))
        except ValidationError as exc:
            entry_id = entry.get("id") if isinstance(entry, dict) else None
            logger.warning(
                "Skipping malformed saved view (id=%s) for user_id=%s: %s",
                entry_id,
                user_id,
                exc,
            )
    return valid_views


@router.post("/", response_model=SavedView, status_code=201)
def create_saved_view(payload: SavedViewCreate, user_id: str = Depends(get_user_id)):
    view = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "filters": payload.filters.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    def _mutate(views: List[dict]) -> List[dict]:
        if len(views) >= MAX_SAVED_VIEWS_PER_USER:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"You have reached the maximum of {MAX_SAVED_VIEWS_PER_USER} "
                    "saved views. Delete one before creating another."
                ),
            )
        return views + [view]

    _atomic_mutate(user_id, _mutate)
    return view


@router.delete("/{view_id}", status_code=204)
def delete_saved_view(view_id: str, user_id: str = Depends(get_user_id)):
    def _mutate(views: List[dict]) -> List[dict]:
        remaining = [v for v in views if v.get("id") != view_id]
        if len(remaining) == len(views):
            raise HTTPException(status_code=404, detail="Saved view not found.")
        return remaining

    _atomic_mutate(user_id, _mutate)
