"""Saved filter-view presets for the accounts screen (mobile MVP).

Stored in Redis (keyed per user) rather than Postgres — this is a small,
low-stakes preference blob, and Redis is already deployed for
Celery/events (see app/services/event_publisher.py). If durability
guarantees ever need to be stronger, move this to a proper table; the
route contract here would stay the same.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import List

import redis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db_helpers import get_user_id

router = APIRouter()

_redis_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(redis_url, decode_responses=True)
    return _redis_client


def _redis_key(user_id: str) -> str:
    return f"saved_views:{user_id}"


class SavedViewFilters(BaseModel):
    account_ids: List[str] = Field(default_factory=list)
    account_types: List[str] = Field(default_factory=list)
    currencies: List[str] = Field(default_factory=list)


class SavedViewCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    filters: SavedViewFilters


class SavedView(SavedViewCreate):
    id: str
    created_at: str


def _load(user_id: str) -> List[dict]:
    raw = get_redis().get(_redis_key(user_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def _save(user_id: str, views: List[dict]) -> None:
    get_redis().set(_redis_key(user_id), json.dumps(views))


@router.get("/", response_model=List[SavedView])
def list_saved_views(user_id: str = Depends(get_user_id)):
    return _load(user_id)


@router.post("/", response_model=SavedView, status_code=201)
def create_saved_view(payload: SavedViewCreate, user_id: str = Depends(get_user_id)):
    views = _load(user_id)
    view = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "filters": payload.filters.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    views.append(view)
    _save(user_id, views)
    return view


@router.delete("/{view_id}", status_code=204)
def delete_saved_view(view_id: str, user_id: str = Depends(get_user_id)):
    views = _load(user_id)
    remaining = [v for v in views if v["id"] != view_id]
    if len(remaining) == len(views):
        raise HTTPException(status_code=404, detail="Saved view not found.")
    _save(user_id, remaining)
