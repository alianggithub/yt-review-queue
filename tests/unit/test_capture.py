"""Unit tests for the capture service."""
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timezone

import pytest
from yt_review_queue.capture import capture_bookmark, get_queue
from yt_review_queue.identity import is_authorized, resolve_account

# Inline schema (matches migrations/001_initial.sql) so tests don't depend on db.py
SCHEMA = """
CREATE TABLE app_account (
    id TEXT PRIMARY KEY, display_name TEXT NOT NULL, timezone TEXT DEFAULT 'UTC',
    created_at TEXT DEFAULT (datetime('now')), disabled_at TEXT);
CREATE TABLE telegram_principal (
    telegram_user_id TEXT PRIMARY KEY, display_name TEXT, active INTEGER DEFAULT 1,
    first_seen_at TEXT DEFAULT (datetime('now')));
CREATE TABLE account_membership (
    app_account_id TEXT NOT NULL REFERENCES app_account(id),
    telegram_user_id TEXT NOT NULL REFERENCES telegram_principal(telegram_user_id),
    role TEXT DEFAULT 'member', is_default INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (app_account_id, telegram_user_id));
CREATE TABLE bookmark (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_account_id TEXT NOT NULL REFERENCES app_account(id),
    telegram_update_id TEXT NOT NULL,
    telegram_user_id TEXT NOT NULL REFERENCES telegram_principal(telegram_user_id),
    captured_at TEXT NOT NULL, received_at TEXT NOT NULL,
    priority INTEGER NOT NULL CHECK (priority BETWEEN 0 AND 5),
    note TEXT,
    source_state TEXT NOT NULL DEFAULT 'awaiting_history',
    watch_state TEXT NOT NULL DEFAULT 'queued',
    selected_match_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE (app_account_id, telegram_update_id));
"""


@pytest.fixture
def conn(tmp_path):
    db = sqlite3.connect(str(tmp_path / "test.db"))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    # Seed account + principal + membership
    db.execute("INSERT INTO app_account (id, display_name) VALUES ('acc-1', 'Test')")
    db.execute("INSERT INTO telegram_principal (telegram_user_id, display_name) VALUES ('12345', 'User')")
    db.execute("INSERT INTO account_membership (app_account_id, telegram_user_id, role, is_default) VALUES ('acc-1', '12345', 'owner', 1)")
    db.commit()
    return db


def test_priority_0_dismissed(conn):
    bm_id = capture_bookmark(conn, "12345", "upd-1", 1721000000, "acc-1", 0, None)
    row = conn.execute("SELECT watch_state FROM bookmark WHERE id=?", (bm_id,)).fetchone()
    assert row["watch_state"] == "dismissed"


def test_priority_5_queued(conn):
    bm_id = capture_bookmark(conn, "12345", "upd-2", 1721000000, "acc-1", 5, "check this")
    row = conn.execute("SELECT watch_state, source_state, note FROM bookmark WHERE id=?", (bm_id,)).fetchone()
    assert row["watch_state"] == "queued"
    assert row["source_state"] == "awaiting_history"
    assert row["note"] == "check this"


def test_duplicate_update_id_returns_existing(conn):
    id1 = capture_bookmark(conn, "12345", "dup-1", 1721000000, "acc-1", 3, None)
    id2 = capture_bookmark(conn, "12345", "dup-1", 1721000000, "acc-1", 3, None)
    assert id1 == id2, "Duplicate update_id should return existing bookmark id"


def test_captured_at_from_message_date(conn):
    # Use a distinctive epoch
    epoch = 1721000000
    before_server = datetime.now(tz=timezone.utc).isoformat()
    bm_id = capture_bookmark(conn, "12345", "upd-ts", epoch, "acc-1", 3, None)
    row = conn.execute("SELECT captured_at, received_at FROM bookmark WHERE id=?", (bm_id,)).fetchone()
    expected_captured = datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    assert row["captured_at"] == expected_captured
    # received_at should be different (server time, not message time)
    assert row["received_at"] != row["captured_at"]


def test_queue_newest_first(conn):
    # Insert 3 bookmarks with different timestamps
    times = [1721000000, 1721001000, 1721000500]
    for i, ts in enumerate(times):
        capture_bookmark(conn, "12345", f"upd-{i}", ts, "acc-1", 3, None)
    queue = get_queue(conn, "acc-1")
    assert len(queue) == 3
    assert queue[0]["captured_at"] > queue[1]["captured_at"] > queue[2]["captured_at"]


def test_is_authorized_unknown_user(conn):
    assert is_authorized(conn, "99999") is False


def test_is_authorized_active_user(conn):
    assert is_authorized(conn, "12345") is True


def test_is_authorized_disabled_user(conn):
    conn.execute("UPDATE telegram_principal SET active=0 WHERE telegram_user_id='12345'")
    conn.commit()
    assert is_authorized(conn, "12345") is False


def test_resolve_account_unauthorized(conn):
    account, err = resolve_account(conn, "99999")
    assert account is None
    assert err == "unauthorized"


def test_resolve_account_single(conn):
    account, err = resolve_account(conn, "12345")
    assert account == "acc-1"
    assert err is None


def test_resolve_account_ambiguous(conn):
    # Add a second account + membership, and remove default from first
    conn.execute("UPDATE account_membership SET is_default=0 WHERE app_account_id='acc-1'")
    conn.execute("INSERT INTO app_account (id, display_name) VALUES ('acc-2', 'Other')")
    conn.execute("INSERT INTO account_membership (app_account_id, telegram_user_id, role, is_default) VALUES ('acc-2', '12345', 'member', 0)")
    conn.commit()
    account, err = resolve_account(conn, "12345")
    assert account is None
    assert err == "ambiguous"
