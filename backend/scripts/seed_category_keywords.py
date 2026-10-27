"""
Seed / refresh `categorization_instructions` + descriptions for a user's
categories using the example keyword lists Giannis provided.

Run:
    cd backend && python -m scripts.seed_category_keywords <user_id>

After seeding, call `CategoryEmbeddingService.refresh_category_embeddings(
    user_id, force=True)` so the anchor vectors reflect the new keywords.
"""
from __future__ import annotations

import sys
from typing import Dict, Tuple

from app.database import SessionLocal
from app.models import Category
from app.services.category_embedding import CategoryEmbeddingService


# name → (description, categorization_instructions)
SEED: Dict[str, Tuple[str, str]] = {
    "Side Projects": (
        "SaaS subscriptions, hosting, domains, AI tools for personal side projects.",
        "Keywords: Cloudflare, Vercel, Namecheap, OpenAI, Perplexity, Claude.ai, "
        "Moneybird, Framer, Tally.so, dub.co, LangChain, Elest.io, Canva, Revo Pro, "
        "unsend.dev, Railway, Upstash, Resend, Cursor, T3 Chat, Huggingface, AWS EMEA, "
        "Google Workspace Syllogic, Teamwork.",
    ),
    "Groceries": (
        "Supermarkets and grocery delivery.",
        "Keywords: Jumbo, Albert Heijn, AH to go, Lidl, Aldi, Picnic, Sklavenitis, "
        "Spar City, Polat International, Carrefour.",
    ),
    "Internal Transfer": (
        "Money moved between your own accounts — not a real income/expense.",
        "Patterns: Apple Pay Top-Up by *, eCom Apple Pay Revolut, To/From Instant Access "
        "Savings, To EUR Pro, To investment account, OBA topup, Exchanged to BTC, IBKR, "
        "Interactive Brokers, Beleggers Spaarrekening, Long-term savings, Short-term savings.",
    ),
    "Food & Dining": (
        "Restaurants, cafes, food delivery and bar bills.",
        "Keywords: Efood, Paradosiako, Mpakalikon, Diatiriteo, Thessalia, Bolosis, "
        "O Tseligkas, Grigorios Kaisaris, Uber Eats, Deliveroo, Thuisbezorgd, Starbucks, "
        "McDonald's. Also: Tikkie splits whose description mentions food/restaurant.",
    ),
}


def seed(user_id: str) -> None:
    db = SessionLocal()
    try:
        cats = db.query(Category).filter(Category.user_id == user_id).all()
        by_name = {c.name.strip().lower(): c for c in cats}

        touched = 0
        for name, (desc, hints) in SEED.items():
            cat = by_name.get(name.lower())
            if cat is None:
                print(f"[skip] Category '{name}' not found for user {user_id}")
                continue
            cat.description = desc
            cat.categorization_instructions = hints
            touched += 1
            print(f"[ok]   {name}: instructions updated")

        if touched:
            db.commit()
            print(f"\nCommitted {touched} category updates.")
            embedder = CategoryEmbeddingService(db)
            refreshed = embedder.refresh_category_embeddings(user_id=user_id, force=True)
            print(f"Refreshed {refreshed} category embeddings.")
        else:
            print("No matching categories found; nothing to do.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.seed_category_keywords <user_id>", file=sys.stderr)
        sys.exit(2)
    seed(sys.argv[1])
