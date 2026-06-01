"""
Embedding-based semantic matching layer for transaction categorization.

Sits between the rigid keyword/deterministic tier and the LLM fallback:

  user override  →  deterministic keywords  →  [embedding tier]  →  batch LLM

For each category we store an "anchor" embedding built from name + description
+ categorization_instructions. For each transaction we embed the
merchant + description text and find the top-k closest categories by cosine
similarity. If the top match is confidently above a threshold AND meaningfully
ahead of the runner-up we accept it; otherwise we defer to the LLM.

This gives us:
  - Tolerance to spelling / spacing / accent variation that rigid rules miss
  - Deterministic cost (one embedding call per new transaction, ~$0.00001 each)
  - A much better signal for the LLM to anchor on when we do fall through
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.models import Category

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("CATEGORIZATION_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = 1536

# Cosine similarity in [-1, 1]; pgvector returns cosine *distance* in [0, 2].
# Similarity = 1 - distance.
ACCEPT_SIMILARITY = float(os.getenv("CATEGORIZATION_EMBEDDING_ACCEPT", "0.78"))
MARGIN_OVER_RUNNER_UP = float(os.getenv("CATEGORIZATION_EMBEDDING_MARGIN", "0.06"))


@dataclass
class EmbeddingMatch:
    category: Category
    similarity: float
    runner_up_similarity: Optional[float]

    @property
    def confidence(self) -> float:
        """Map similarity + margin into a 0-100 confidence score."""
        margin = (self.similarity - (self.runner_up_similarity or 0.0))
        # 0.78 sim with 0.06 margin → ~80. 0.9 sim with 0.15 margin → ~98.
        raw = self.similarity * 90.0 + max(0.0, margin) * 50.0
        return max(0.0, min(100.0, raw))


def build_category_anchor_text(category: Category) -> str:
    """Flatten name + description + keywords into a single embedding input."""
    parts: List[str] = [category.name]
    if category.description:
        parts.append(category.description.strip())
    hints = (category.categorization_instructions or "").strip()
    if hints:
        parts.append(hints)
    return " — ".join(parts)


def build_transaction_text(
    description: Optional[str],
    merchant: Optional[str],
    transaction_type: Optional[str] = None,
) -> str:
    """Flatten transaction fields into embedding input. Merchant first (highest signal)."""
    parts: List[str] = []
    if merchant:
        parts.append(f"Merchant: {merchant}")
    if description:
        parts.append(f"Description: {description}")
    if transaction_type:
        parts.append(f"Type: {transaction_type}")
    return " | ".join(parts) if parts else "unknown"


class CategoryEmbeddingService:
    """OpenAI-backed embedding service for categories and transactions."""

    def __init__(self, db: Session, openai_client=None):
        self.db = db
        self._client = openai_client  # Lazy-init if None

    def _get_client(self):
        if self._client is not None:
            return self._client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key)
            return self._client
        except Exception as e:
            logger.warning(f"Could not initialize OpenAI client for embeddings: {e}")
            return None

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Embed a batch of texts. Returns [] if OpenAI is unavailable."""
        texts = [t or "" for t in texts]
        if not texts:
            return []
        client = self._get_client()
        if client is None:
            return []
        # `dimensions` is only supported by text-embedding-3* models. Older
        # models (e.g. text-embedding-ada-002) 400 if we pass it. We still
        # validate vector length after the call so a mismatch can't slip into
        # the vector(1536) column either way.
        extra: dict = (
            {"dimensions": EMBEDDING_DIMENSIONS}
            if EMBEDDING_MODEL.startswith("text-embedding-3")
            else {}
        )
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=list(texts),
                **extra,
            )
            vectors = [d.embedding for d in response.data]
            for v in vectors:
                if len(v) != EMBEDDING_DIMENSIONS:
                    logger.error(
                        f"Embedding dimension mismatch: got {len(v)}, expected "
                        f"{EMBEDDING_DIMENSIONS} for model {EMBEDDING_MODEL!r}; "
                        f"refusing to return vectors"
                    )
                    return []
            return vectors
        except Exception as e:
            logger.warning(f"Embedding call failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Category anchor maintenance
    # ------------------------------------------------------------------

    def refresh_category_embeddings(
        self,
        user_id: str,
        category_ids: Optional[Iterable[str]] = None,
        force: bool = False,
    ) -> int:
        """(Re)compute embeddings for categories.

        By default only categories whose embedding is NULL are refreshed.
        Pass `force=True` to rebuild all category anchors (use after editing
        `categorization_instructions`).
        """
        q = self.db.query(Category).filter(Category.user_id == user_id)
        if category_ids:
            q = q.filter(Category.id.in_(list(category_ids)))
        if not force:
            q = q.filter(Category.embedding.is_(None))
        categories = q.all()
        if not categories:
            return 0

        texts = [build_category_anchor_text(c) for c in categories]
        vectors = self.embed(texts)
        if not vectors:
            logger.warning("No embeddings returned; skipping category anchor refresh")
            return 0

        updated = 0
        for cat, vec in zip(categories, vectors):
            cat.embedding = vec
            updated += 1
        self.db.commit()
        logger.info(f"Refreshed embeddings for {updated} categories")
        return updated

    # ------------------------------------------------------------------
    # Transaction-side matching
    # ------------------------------------------------------------------

    def match_category(
        self,
        user_id: str,
        description: Optional[str],
        merchant: Optional[str],
        transaction_type: Optional[str] = None,
        precomputed_embedding: Optional[List[float]] = None,
    ) -> Optional[EmbeddingMatch]:
        """Embed the transaction, find top candidate category, apply accept thresholds."""
        if precomputed_embedding is None:
            vectors = self.embed([build_transaction_text(description, merchant, transaction_type)])
            if not vectors:
                return None
            vec = vectors[0]
        else:
            vec = precomputed_embedding

        txn_type = (transaction_type or "").lower()
        if txn_type in ("expense", "expenses", "debit"):
            type_filter = "('expense', 'transfer')"
        elif txn_type in ("income", "revenue", "credit"):
            type_filter = "('income', 'transfer')"
        else:
            type_filter = "('expense', 'income', 'transfer')"

        # pgvector `<=>` returns cosine distance. Lower is better.
        vec_literal = "[" + ",".join(str(x) for x in vec) + "]"
        rows = self.db.execute(
            sql_text(
                f"""
                SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) AS similarity
                FROM categories
                WHERE user_id = :user_id
                  AND embedding IS NOT NULL
                  AND category_type IN {type_filter}
                  AND COALESCE(hide_from_selection, FALSE) = FALSE
                ORDER BY embedding <=> CAST(:vec AS vector)
                LIMIT 2
                """
            ),
            {"vec": vec_literal, "user_id": user_id},
        ).fetchall()

        if not rows:
            return None

        top_id, top_sim = rows[0]
        runner_sim = rows[1][1] if len(rows) > 1 else None

        if top_sim < ACCEPT_SIMILARITY:
            logger.debug(
                f"Embedding top sim {top_sim:.3f} below accept threshold "
                f"{ACCEPT_SIMILARITY}; deferring to LLM"
            )
            return None
        if runner_sim is not None and (top_sim - runner_sim) < MARGIN_OVER_RUNNER_UP:
            logger.debug(
                f"Embedding top sim {top_sim:.3f} but runner-up {runner_sim:.3f} is too close "
                f"(margin < {MARGIN_OVER_RUNNER_UP}); deferring to LLM"
            )
            return None

        top_cat = self.db.query(Category).filter(Category.id == top_id).first()
        if top_cat is None:
            return None
        return EmbeddingMatch(
            category=top_cat,
            similarity=float(top_sim),
            runner_up_similarity=float(runner_sim) if runner_sim is not None else None,
        )

    def match_categories_batch(
        self,
        user_id: str,
        transactions: List[dict],
    ) -> Tuple[dict, List[List[float]]]:
        """Batch path used by the post-import pipeline.

        Returns:
            (index_to_match, per_transaction_embeddings) where index_to_match
            holds only the high-confidence matches the caller should accept.
            Indexes missing from the dict should be passed to the LLM.
        """
        if not transactions:
            return {}, []
        texts = [
            build_transaction_text(t.get("description"), t.get("merchant"), t.get("transaction_type"))
            for t in transactions
        ]
        vectors = self.embed(texts)
        if not vectors:
            return {}, []

        accepted: dict = {}
        for txn, vec in zip(transactions, vectors):
            match = self.match_category(
                user_id=user_id,
                description=txn.get("description"),
                merchant=txn.get("merchant"),
                transaction_type=txn.get("transaction_type"),
                precomputed_embedding=vec,
            )
            if match is not None:
                accepted[txn["index"]] = match
        return accepted, vectors
