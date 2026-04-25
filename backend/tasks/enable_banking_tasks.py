"""
Celery tasks for Enable Banking sync and consent management.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import redis
from sqlalchemy.orm import Session

from celery_app import celery_app
from app.database import SessionLocal
from app.models import BankConnection, Account
from app.integrations.enable_banking_adapter import EnableBankingAdapter
from app.integrations.enable_banking_auth import EnableBankingClient
from app.services.sync_service import SyncService
from app.security.data_encryption import decrypt_with_fallback
from tasks.post_import_pipeline import post_import_pipeline

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SYNC_COOLDOWN_SECONDS = 300    # 5 min since last completed sync
SYNC_IN_PROGRESS_TIMEOUT = 600  # 10 min since sync started (covers 730-day initial load)


def _should_skip_sync(connection) -> bool:
    """Return True if a sync should be skipped due to recency or in-progress state."""
    now = datetime.now(timezone.utc)

    if connection.last_synced_at:
        last = connection.last_synced_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if (now - last).total_seconds() < SYNC_COOLDOWN_SECONDS:
            return True

    if connection.sync_started_at:
        started = connection.sync_started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if (now - started).total_seconds() < SYNC_IN_PROGRESS_TIMEOUT:
            return True

    return False


def _account_sync_start_date(account, connection) -> "date":
    """Return the start date for syncing a single account.

    Previously-synced accounts start from last_synced_at - 1 day (incremental).
    New accounts (never synced) use the connection's full initial_sync_days lookback.
    """
    from datetime import date as _date
    if account.last_synced_at is not None:
        last = account.last_synced_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return (last - timedelta(days=1)).date()
    sync_days = connection.initial_sync_days or 90
    return (datetime.now(timezone.utc) - timedelta(days=sync_days)).date()


_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _set_sync_progress(connection_id: str, data: dict) -> None:
    try:
        key = f"sync_progress:{connection_id}"
        _get_redis().setex(key, 3600, json.dumps(data))
    except Exception as e:
        logger.warning(f"Failed to write sync progress to Redis: {e}")


def _clear_sync_progress(connection_id: str) -> None:
    try:
        _get_redis().delete(f"sync_progress:{connection_id}")
    except Exception:
        pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def sync_bank_connection(self, connection_id: str):
    """
    Sync a single bank connection: fetch balances + transactions for all accounts.
    Runs through SyncService for categorization, enrichment, and subscription matching.
    """
    db: Session = SessionLocal()
    try:
        connection = db.query(BankConnection).filter(
            BankConnection.id == connection_id,
        ).first()

        if not connection:
            logger.error(f"Bank connection {connection_id} not found")
            return {"error": "Connection not found"}

        if connection.status not in ("active",):
            logger.info(f"Skipping sync for connection {connection_id} with status {connection.status}")
            return {"skipped": True, "reason": f"Status is {connection.status}"}

        # Idempotency guard — skip if a sync ran recently or is still in progress
        if _should_skip_sync(connection):
            logger.info(f"[SYNC] Skipped for connection {connection_id}: too recent or in progress")
            return {"skipped": True, "reason": "sync_too_recent"}

        # Mark sync as in progress before any API calls
        connection.sync_started_at = datetime.now(timezone.utc)
        db.commit()
        _sync_started_at_cleared = False  # tracks whether the success path already cleared it

        client = EnableBankingClient()
        adapter = EnableBankingAdapter(
            session_id=connection.session_id,
            client=client,
        )

        # Capture before any sync updates last_synced_at
        is_initial_sync = connection.last_synced_at is None

        # end_date is shared across all accounts; start_date is computed per-account below
        end_date = datetime.now(timezone.utc)

        # LLM categorization is intentionally disabled here.
        # Inline per-transaction LLM calls during sync waste tokens and slow the import.
        # The post_import_pipeline (step 3) runs a single batch LLM pass over all
        # touched transactions after sync completes — more efficient and equally accurate.
        # Do NOT set use_llm_categorization=True here without removing the batch step.
        sync_service = SyncService(db, user_id=connection.user_id, use_llm_categorization=False)

        # Get accounts linked to this connection
        accounts = db.query(Account).filter(
            Account.bank_connection_id == connection.id,
        ).all()

        # Backfill account-level IBAN on synced accounts that don't have it yet.
        # This is independent of the per-account sync_transactions loop below;
        # adapter.fetch_accounts() returns the IBAN exposed by EB's session
        # data, and SyncService._set_account_iban_fields treats IBAN as
        # immutable (no overwrite once set). Without this hook, the
        # InternalTransferService can't recognize transfers between two
        # synced accounts because it won't know which IBANs are the user's.
        try:
            account_data_list = adapter.fetch_accounts()
            account_data_by_uid = {
                ad.external_id: ad for ad in account_data_list
            }
            for acc in accounts:
                acc_uid = decrypt_with_fallback(
                    acc.external_id_ciphertext, acc.external_id
                )
                if not acc_uid:
                    continue
                ad = account_data_by_uid.get(acc_uid)
                if ad is None:
                    continue
                sync_service._set_account_iban_fields(acc, ad.iban)
            db.commit()
        except Exception as e:
            # Don't fail the sync if account-level fetch hiccups — the per-account
            # transaction sync below has its own error handling, and IBAN backfill
            # can retry on the next sync.
            logger.warning(
                f"[SYNC] IBAN backfill skipped for connection {connection_id}: {e}"
            )
            db.rollback()

        total_created = 0
        total_updated = 0
        all_created_ids: list[str] = []
        all_updated_ids: list[str] = []
        synced_account_ids: list[str] = []

        accounts_total = len(accounts)
        sync_started_at = datetime.now(timezone.utc).isoformat()
        _set_sync_progress(connection_id, {
            "stage": "syncing",
            "accounts_done": 0,
            "accounts_total": accounts_total,
            "transactions_created": 0,
            "transactions_updated": 0,
            "started_at": sync_started_at,
        })

        for i, account in enumerate(accounts):
            account_uid = decrypt_with_fallback(
                account.external_id_ciphertext,
                account.external_id,
            )
            if not account_uid:
                logger.warning(f"No external_id for account {account.id}, skipping")
                continue

            # Fetch and update balances.
            # Priority order of ISO 20022 balance types:
            #   CLAV/ITAV = (interim) available — most accurate "what you can spend"
            #   CLBD      = closing booked — authoritative, excludes pending
            #   XPCD      = expected — booked + pending
            #   PRCD      = previously closed booked
            #   OTHR      = bank-defined fallback
            # ABN AMRO via Enable Banking does not return CLAV/ITAV, so fall through
            # the priority list and finally pick the first returned balance.
            try:
                balance_data = adapter.fetch_balances(account_uid)
                balances = balance_data.get("balances", [])
                priority = ("CLAV", "ITAV", "CLBD", "XPCD", "PRCD", "OTHR")
                chosen = None
                for pref in priority:
                    for bal in balances:
                        if bal.get("balance_type", "").upper() == pref:
                            chosen = bal
                            break
                    if chosen:
                        break
                if chosen is None and balances:
                    chosen = balances[0]
                if chosen is not None:
                    account.balance_available = chosen["balance_amount"]["amount"]
                    account.balance_is_anchored = True
                else:
                    logger.warning(
                        f"No balances returned by Enable Banking for account {account.id}"
                    )
            except Exception as e:
                logger.warning(f"Failed to fetch balances for account {account.id}: {e}")

            # Sync transactions via SyncService
            try:
                start_date = _account_sync_start_date(account, connection)  # per-account
                created, updated, created_ids, updated_ids = sync_service.sync_transactions(
                    adapter=adapter,
                    account=account,
                    start_date=start_date,
                    end_date=end_date,
                )
                total_created += created
                total_updated += updated
                all_created_ids.extend(created_ids)
                all_updated_ids.extend(updated_ids)
                synced_account_ids.append(str(account.id))
            except Exception as e:
                logger.error(f"Failed to sync transactions for account {account.id}: {e}")
                raise

            account.last_synced_at = datetime.now(timezone.utc)
            _set_sync_progress(connection_id, {
                "stage": "syncing",
                "accounts_done": i + 1,
                "accounts_total": accounts_total,
                "transactions_created": total_created,
                "transactions_updated": total_updated,
                "started_at": sync_started_at,
            })

            # Anchor balance: back-calculate starting_balance so functional_balance = balance_available.
            # This fixes the displayed balance for accounts that only have partial history imported.
            if account.balance_is_anchored and account.balance_available is not None:
                from sqlalchemy import func as _sa_func2
                from app.models import Transaction
                _txn_sum_result = db.query(_sa_func2.sum(Transaction.amount)).filter(
                    Transaction.user_id == connection.user_id,
                    Transaction.account_id == account.id,
                ).scalar()
                _txn_sum = Decimal(str(_txn_sum_result)) if _txn_sum_result else Decimal("0")
                _balance_av = Decimal(str(account.balance_available))
                account.starting_balance = _balance_av - _txn_sum
                account.functional_balance = _balance_av

        connection.last_synced_at = datetime.now(timezone.utc)
        connection.sync_started_at = None  # clear atomically with last_synced_at
        connection.last_sync_error = None
        db.commit()
        _sync_started_at_cleared = True
        _clear_sync_progress(connection_id)

        # Chain to shared post-processing pipeline (run if any transactions were touched).
        # Pass all created + updated IDs so the pipeline can batch-categorize, compute FX
        # rates, and run subscription detection on the full set of touched transactions.
        all_touched_ids = list(dict.fromkeys(all_created_ids + all_updated_ids))  # dedup, preserve order
        if all_touched_ids or total_updated > 0:
            post_import_pipeline.delay(
                user_id=str(connection.user_id),
                account_ids=synced_account_ids,
                transaction_ids=all_touched_ids,
                is_initial_sync=is_initial_sync,
            )

        logger.info(
            f"Synced connection {connection_id}: "
            f"{total_created} created, {total_updated} updated"
        )
        return {
            "connection_id": connection_id,
            "transactions_created": total_created,
            "transactions_updated": total_updated,
        }

    except Exception as e:
        logger.error(f"Sync failed for connection {connection_id}: {e}", exc_info=True)
        # Mark error on connection
        try:
            connection = db.query(BankConnection).filter(
                BankConnection.id == connection_id,
            ).first()
            if connection:
                error_msg = str(e)
                # Detect expired consent (only from Enable Banking API errors, not internal auth)
                is_eb_auth_error = (
                    ("401" in error_msg or "403" in error_msg)
                    and "enablebanking" in error_msg.lower()
                ) or "consent" in error_msg.lower()
                if is_eb_auth_error:
                    connection.status = "expired"
                    connection.last_sync_error = "Consent expired. Please reconnect."
                else:
                    connection.last_sync_error = error_msg[:500]
                db.commit()
        except Exception:
            pass
        _clear_sync_progress(connection_id)
        raise self.retry(exc=e)
    finally:
        # Clear in-progress marker if not already cleared by the success path
        if not _sync_started_at_cleared:
            try:
                conn = db.query(BankConnection).filter(BankConnection.id == connection_id).first()
                if conn:
                    conn.sync_started_at = None
                    db.commit()
            except Exception:
                pass
        db.close()


@celery_app.task
def sync_all_bank_connections():
    """
    Periodic task: dispatch sync for all active bank connections.
    Runs every 6 hours via Celery beat.
    """
    db: Session = SessionLocal()
    try:
        connections = db.query(BankConnection).filter(
            BankConnection.status == "active",
        ).all()

        dispatched = 0
        for conn in connections:
            try:
                sync_bank_connection.delay(str(conn.id))
                dispatched += 1
            except Exception as e:
                logger.error(f"Failed to dispatch sync for connection {conn.id}: {e}")

        logger.info(f"Dispatched sync for {dispatched} active connections")
        return {"dispatched": dispatched}
    finally:
        db.close()


@celery_app.task
def check_consent_expiry():
    """
    Daily task: update status for connections with expired consents.
    Frontend reads consent_expires_at directly for banner display.
    """
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)

        # Mark expired connections
        expired = db.query(BankConnection).filter(
            BankConnection.status == "active",
            BankConnection.consent_expires_at <= now,
        ).all()

        for conn in expired:
            conn.status = "expired"
            conn.last_sync_error = "Consent expired. Please reconnect your bank."
            logger.info(f"Marked connection {conn.id} ({conn.aspsp_name}) as expired")

        db.commit()

        logger.info(f"Consent expiry check: marked {len(expired)} connections as expired")
        return {"expired_count": len(expired)}
    finally:
        db.close()
