"""Seed/reset deterministic demo data for a shared demo user.

Usage examples:
  python postgres_migration/seed_demo_data.py --user-email demo@example.com --mode reset
  python postgres_migration/seed_demo_data.py --user-id <id> --from-date 2025-01-01 --to-date 2026-03-01 --mode reset
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

# Add backend directory to import path when executed from backend/ or backend/postgres_migration/
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database import Base, SessionLocal, engine
from app.services.demo_seed_service import DEMO_DEFAULT_START_DATE, DemoSeedService


def _parse_iso_date(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date '{raw}'. Use YYYY-MM-DD format.") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed deterministic demo data for a specific existing user")
    parser.add_argument("--user-id", help="Existing BetterAuth user ID to seed")
    parser.add_argument("--user-email", help="Existing BetterAuth user email to seed")
    parser.add_argument(
        "--from-date",
        type=_parse_iso_date,
        default=DEMO_DEFAULT_START_DATE,
        help="Start date for generated transactions (default: 2025-01-01)",
    )
    parser.add_argument(
        "--to-date",
        type=_parse_iso_date,
        default=date.today(),
        help="End date for generated transactions (default: today)",
    )
    parser.add_argument(
        "--mode",
        choices=["reset", "seed"],
        default="reset",
        help="reset: clear existing financial data first; seed: append without clearing",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=int(os.getenv("DEMO_SEED_RANDOM_SEED", "42")),
        help="Deterministic random seed for demo generator",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.user_id and not args.user_email:
        parser.error("Provide --user-id or --user-email")

    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        service = DemoSeedService(session, random_seed=args.random_seed)
        user = service.resolve_user(user_id=args.user_id, email=args.user_email)
        summary = service.seed_for_user(
            user=user,
            start_date=args.from_date,
            end_date=args.to_date,
            reset=(args.mode == "reset"),
        )

        print("\nDemo seed completed successfully")
        print(f"- user_id: {summary['user_id']}")
        print(f"- user_email: {summary['user_email']}")
        print(f"- reset_mode: {summary['reset']}")
        print(f"- accounts_created: {summary['accounts_created']}")
        print(f"- categories_created: {summary['categories_created']}")
        print(f"- transactions_created: {summary['transactions_created']}")
        print(f"- currencies: {', '.join(summary['currencies'])}")
        print(
            f"- date_range: {summary['date_range']['start']} -> {summary['date_range']['end']}"
        )

        fx = summary.get("exchange_rates_synced")
        if isinstance(fx, dict) and fx.get("error"):
            print(f"- exchange_rates: error ({fx['error']})")
        elif isinstance(fx, dict):
            print(
                f"- exchange_rates: dates_processed={fx.get('dates_processed', 0)}, "
                f"total_rates_stored={fx.get('total_rates_stored', 0)}"
            )

        functional = summary.get("functional_amounts", {})
        print(
            f"- functional_amounts: updated={functional.get('updated', 0)}, "
            f"skipped={functional.get('skipped', 0)}, failed={functional.get('failed', 0)}"
        )

        balances = summary.get("balances_calculated", {})
        print(
            f"- balances: updated={balances.get('accounts_updated', 0)}, "
            f"failed={balances.get('accounts_failed', 0)}"
        )

        timeseries = summary.get("timeseries_calculated", {})
        print(
            f"- timeseries: accounts_processed={timeseries.get('accounts_processed', 0)}, "
            f"records_stored={timeseries.get('total_records_stored', 0)}"
        )

        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Demo seeding failed: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
