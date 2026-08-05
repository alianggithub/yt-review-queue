"""Bookmark capture service.

Implements the capture pipeline from DESIGN-v2.md §9:
- insert with source_state='awaiting_history'
- priority 0 -> watch_state='dismissed'
- captured_at from Telegram message.date (not server time)
- idempotent on (app_account_id, telegram_update_id)
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def capture_bookmark(
    conn: sqlite3.Connection,
    telegram_user_id: str,
    telegram_update_id: str,
    message_date_epoch: int,
    account_id: str,
    priority: int,
    note: str | None = None,
) -> int:
    """Insert a bookmark and return its row id.

    If (account_id, telegram_update_id) already exists, return the existing id
    without inserting a duplicate (idempotency, §9 step 2).
    """
    # Check for existing (idempotency)
    row = conn.execute(
        "SELECT id FROM bookmark WHERE app_account_id=? AND telegram_update_id=?",
        (account_id, telegram_update_id),
    ).fetchone()
    if row is not None:
        return row["id"] if isinstance(row, sqlite3.Row) else row[0]

    captured_at = datetime.fromtimestamp(message_date_epoch, tz=timezone.utc).isoformat()
    received_at = datetime.now(tz=timezone.utc).isoformat()

    watch_state = "dismissed" if priority == 0 else "queued"

    cursor = conn.execute(
        """
        INSERT INTO bookmark
            (app_account_id, telegram_update_id, telegram_user_id,
             captured_at, received_at, priority, note, source_state, watch_state)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'awaiting_history', ?)
        """,
        (account_id, telegram_update_id, str(telegram_user_id),
         captured_at, received_at, priority, note, watch_state),
    )
    conn.commit()
    return cursor.lastrowid or 0


def get_queue(
    conn: sqlite3.Connection,
    account_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return bookmarks for an account, newest-first (§8.3).

    Ordering: captured_at DESC, id DESC (stable secondary sort).
    """
    rows = conn.execute(
        """
        SELECT id, app_account_id, telegram_update_id, telegram_user_id,
               captured_at, received_at, priority, note,
               source_state, watch_state, selected_match_id
        FROM bookmark
        WHERE app_account_id = ?
        ORDER BY captured_at DESC, id DESC
        LIMIT ?
        """,
        (account_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
