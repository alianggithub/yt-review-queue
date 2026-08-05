"""Identity resolver — maps Telegram users to application accounts.

Implements the authorization flow from DESIGN-v2.md §7 and §9:
1. Check active status (whitelist) before membership lookup
2. Resolve to the sole/default account, or report ambiguity
3. Never allow unrestricted self-binding
"""
from __future__ import annotations

import sqlite3
from typing import Tuple


def is_authorized(conn: sqlite3.Connection, telegram_user_id: str) -> bool:
    """Return True if the Telegram principal is known and active."""
    row = conn.execute(
        "SELECT active FROM telegram_principal WHERE telegram_user_id = ?",
        (str(telegram_user_id),),
    ).fetchone()
    if row is None:
        return False
    active = row["active"] if isinstance(row, sqlite3.Row) else row[0]
    return bool(active)


def resolve_account(
    conn: sqlite3.Connection,
    telegram_user_id: str,
) -> Tuple[str | None, str | None]:
    """Resolve a Telegram user to their application account.

    Returns (account_id, error_msg):
        - (account_id, None) if a single default was found
        - (None, "unauthorized") if principal is unknown or inactive
        - (None, "no_membership") if principal is active but has no account
        - (None, "ambiguous") if multiple accounts with no default
    """
    if not is_authorized(conn, telegram_user_id):
        return (None, "unauthorized")

    rows = conn.execute(
        """
        SELECT am.app_account_id, am.is_default
        FROM account_membership am
        WHERE am.telegram_user_id = ?
        """,
        (str(telegram_user_id),),
    ).fetchall()

    if len(rows) == 0:
        return (None, "no_membership")

    if len(rows) == 1:
        return (rows[0]["app_account_id"], None)

    # Multiple memberships — look for a default
    for row in rows:
        if row["is_default"]:
            return (row["app_account_id"], None)

    return (None, "ambiguous")
