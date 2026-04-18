"""
Celery tasks for Enable Banking sync and consent management.
"""

import json
import logging
import os
from datetime import datetime, timedelta
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

        client = EnableBankingClient()
        adapter = EnableBankingAdapter(
            session_id=connection.session_id,
            client=client,
        )

        # Capture before any sync updates last_synced_at
        is_initial_sync = connection.last_synced_at is None

        # Determine date range for transactions
        if connection.last_synced_at is None:
            # First sync: use user-configured lookback
            sync_days = connection.initial_sync_days or 90
            start_date = (datetime.utcnow() - timedelta(days=sync_days)).date()
        else:
            # Incremental sync: from last sync minus 1 day overlap
            start_date = (connection.last_synced_at - timedelta(days=1)).date()
        end_date = datetime.utcnow()

        sync_service = SyncService(db, user_id=connection.user_id)

        # Get accounts linked to this connection
        accounts = db.query(Account).filter(
            Account.bank_connection_id == connection.id,
        ).all()

        total_created = 0
        total_updated = 0
        all_created_ids: list[str] = []
        synced_account_ids: list[str] = []

        accounts_total = len(accounts)
        sync_started_at = datetime.utcnow().isoformat()
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

            # Fetch and update balances
            try:
                balance_data = adapter.fetch_balances(account_uid)
                balances = balance_data.get("balances", [])
                for bal in balances:
                    bal_type = bal.get("balance_type", "")
                    if bal_type in ("CLAV", "ITAV"):  # Available balance
                        account.balance_available = bal["balance_amount"]["amount"]
                        account.balance_is_anchored = True
                        break
            except Exception as e:
                logger.warning(f"Failed to fetch balances for account {account.id}: {e}")

            # Sync transactions via SyncService
            try:
                created, updated, created_ids = sync_service.sync_transactions(
                    adapter=adapter,
                    account=account,
                    start_date=start_date,
                    end_date=end_date,
                )
                total_created += created
                total_updated += updated
                all_created_ids.extend(created_ids)
                synced_account_ids.append(str(account.id))
            except Exception as e:
                logger.error(f"Failed to sync transactions for account {account.id}: {e}")
                raise

            account.last_synced_at = datetime.utcnow()
            _set_sync_progress(connection_id, {
                "stage": "syncing",
                "accounts_done": i + 1,
                "accounts_total": accounts_total,
                "transactions_created": total_created,
                "transactions_updated": total_updated,
                "started_at": sync_started_at,
            })

        # Recompute functional_balance for all synced accounts
        from sqlalchemy import func as sa_func
        from app.models import Transaction
        for account in accounts:
            transaction_sum_result = db.query(sa_func.sum(Transaction.amount)).filter(
                Transaction.user_id == connection.user_id,
                Transaction.account_id == account.id,
            ).scalar()
            transaction_sum = Decimal(str(transaction_sum_result)) if transaction_sum_result else Decimal("0")
            starting_balance = account.starting_balance or Decimal("0")
            account.functional_balance = transaction_sum + starting_balance

        connection.last_synced_at = datetime.utcnow()
        connection.last_sync_error = None
        db.commit()
        _clear_sync_progress(connection_id)

        # Chain to shared post-processing pipeline (run if any transactions were touched)
        if all_created_ids or total_updated > 0:
            post_import_pipeline.delay(
                user_id=str(connection.user_id),
                account_ids=synced_account_ids,
                transaction_ids=all_created_ids,
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
        now = datetime.utcnow()

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
