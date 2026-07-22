"""
Backfill the `transactions.embedding` column for existing rows.

This script ONLY populates embeddings. It does NOT touch category_system_id,
category_id, categorization_confidence, or categorization_method — existing
categorizations are preserved exactly as-is.

Run:
    cd backend && python -m scripts.backfill_transaction_embeddings <user_id>

Flags:
    --dry-run        Count what would be embedded and exit without API calls.
    --batch-size N   Transactions per OpenAI embeddings call (default: 100, must be > 0).
    --limit N        Cap total rows processed (default: no limit, must be > 0 if set).

Cost: ~$0.00001 per row with text-embedding-3-small, so ~$0.10 per 10k rows.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import List

from app.database import SessionLocal
from app.models import Transaction
from app.services.category_embedding import (
    CategoryEmbeddingService,
    build_transaction_text,
)

logger = logging.getLogger(__name__)


def _positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {raw!r}")
    if value <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {value}")
    return value


def backfill(user_id: str, dry_run: bool, batch_size: int, limit: int | None) -> None:
    if batch_size <= 0:
        raise ValueError(f"batch_size must be > 0, got {batch_size}")
    if limit is not None and limit <= 0:
        raise ValueError(f"limit must be > 0 if set, got {limit}")

    db = SessionLocal()
    try:
        # Fetch only IDs up front so we don't load entire Transaction rows into
        # memory for very large users. We batch-load full rows per chunk below.
        id_query = (
            db.query(Transaction.id)
            .filter(
                Transaction.user_id == user_id,
                Transaction.embedding.is_(None),
            )
            .order_by(Transaction.booked_at.desc(), Transaction.id)
        )
        if limit is not None:
            id_query = id_query.limit(limit)

        pending_ids = [row[0] for row in id_query.all()]
        total = len(pending_ids)
        print(f"Found {total} transaction(s) without embeddings for user {user_id}")

        if total == 0 or dry_run:
            if dry_run:
                print("[dry-run] exiting without writing.")
            return

        embedder = CategoryEmbeddingService(db)
        if embedder._get_client() is None:
            print("OpenAI client unavailable (no OPENAI_API_KEY). Aborting.", file=sys.stderr)
            sys.exit(1)

        done = 0
        for start in range(0, total, batch_size):
            chunk_ids = pending_ids[start : start + batch_size]
            chunk: List[Transaction] = (
                db.query(Transaction)
                .filter(Transaction.id.in_(chunk_ids))
                .all()
            )
            # Preserve the original ordering (in_() doesn't guarantee it).
            chunk.sort(key=lambda t: chunk_ids.index(t.id))

            texts = [
                build_transaction_text(t.description, t.merchant, t.transaction_type)
                for t in chunk
            ]
            vectors = embedder.embed(texts)
            if not vectors or len(vectors) != len(chunk):
                logger.warning(
                    "Embedding batch returned %d vectors for %d rows; skipping chunk",
                    len(vectors),
                    len(chunk),
                )
                # Release chunk rows from the session before the next iteration.
                db.expunge_all()
                continue

            for txn, vec in zip(chunk, vectors):
                txn.embedding = vec

            db.commit()
            db.expunge_all()
            done += len(chunk)
            print(f"  embedded {done}/{total}")

        print(f"Done. Embedded {done}/{total} transactions. Categorization untouched.")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id", help="User ID to backfill")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=_positive_int, default=100)
    parser.add_argument("--limit", type=_positive_int, default=None)
    args = parser.parse_args()
    backfill(
        user_id=args.user_id,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
