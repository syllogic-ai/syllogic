"""Diagnostic: report whether IBKR Flex tokens are shared across BrokerConnections.

Prints a SHA256 fingerprint (first 12 chars) of each connection's flex_token plus
its query IDs — never the plaintext. Run inside the backend service:

    railway run -s backend python scripts/check_ibkr_token_sharing.py
"""
from __future__ import annotations
import hashlib
from collections import defaultdict

from app.database import SessionLocal
from app.models import BrokerConnection, Account
from app.services.credentials_crypto import decrypt


def fp(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def main() -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(BrokerConnection, Account)
            .join(Account, Account.id == BrokerConnection.account_id)
            .filter(BrokerConnection.provider == "ibkr_flex")
            .order_by(BrokerConnection.user_id, BrokerConnection.created_at)
            .all()
        )

        token_groups: dict[str, list[str]] = defaultdict(list)
        missing_token: list[str] = []
        print(f"{'account_id':<38} {'name':<24} {'token_fp':<14} {'qpos_fp':<14} {'qtrd_fp':<14} {'last_status':<12} {'last_error'}")
        for conn, acct in rows:
            try:
                creds = decrypt(conn.credentials_encrypted)
            except Exception as e:
                print(f"{acct.id} {acct.name[:24]:<24} <DECRYPT FAILED: {e}>")
                continue
            raw_token = creds.get("flex_token") or ""
            qp = fp(creds.get("query_id_positions") or "") if (creds.get("query_id_positions") or "") else "<missing>"
            qt = fp(creds.get("query_id_trades") or "") if (creds.get("query_id_trades") or "") else "<missing>"
            if raw_token:
                tfp = fp(raw_token)
                token_groups[tfp].append(str(acct.id))
            else:
                tfp = "<missing>"
                missing_token.append(str(acct.id))
            print(
                f"{str(acct.id):<38} {acct.name[:24]:<24} {tfp:<14} {qp:<14} {qt:<14} "
                f"{(conn.last_sync_status or ''):<12} {(conn.last_sync_error or '')[:60]}"
            )

        print("\nToken-sharing summary:")
        shared = {fp_: ids for fp_, ids in token_groups.items() if len(ids) > 1}
        if not shared:
            print("  No token sharing detected — every IBKR connection with a token uses a distinct flex_token.")
        else:
            for fp_, ids in shared.items():
                print(f"  token_fp={fp_} shared by {len(ids)} accounts:")
                for aid in ids:
                    print(f"    - {aid}")
        if missing_token:
            print(f"\n  WARNING: {len(missing_token)} connection(s) have no flex_token (excluded from sharing analysis):")
            for aid in missing_token:
                print(f"    - {aid}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
