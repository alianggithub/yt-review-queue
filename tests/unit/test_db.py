"""Unit tests for database schema and migration runner."""
import sqlite3
import pytest
from pathlib import Path
from datetime import datetime, timezone

from yt_review_queue.db import init_db, migrate


@pytest.fixture
def db(tmp_path):
    """Fresh database for each test."""
    db_path = tmp_path / "test.sqlite3"
    # Point migrations dir to the real one
    mig_dir = Path(__file__).resolve().parent.parent.parent / "migrations"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn, mig_dir)
    return conn


def _insert_account(conn, account_id="acc-1", display_name="Test"):
    conn.execute(
        "INSERT INTO app_account (id, display_name) VALUES (?, ?)",
        (account_id, display_name),
    )
    conn.commit()


def _insert_principal(conn, tg_id="12345"):
    conn.execute(
        "INSERT INTO telegram_principal (telegram_user_id, display_name, active) VALUES (?, ?, 1)",
        (tg_id, "TestUser"),
    )
    conn.commit()


def test_init_db_creates_all_tables(tmp_path):
    """init_db should create all 9 core tables plus schema_version."""
    db_path = tmp_path / "test.sqlite3"
    conn = init_db(db_path)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    expected = {
        "schema_version",
        "app_account",
        "telegram_principal",
        "account_membership",
        "google_connection",
        "bookmark",
        "activity_event",
        "match_candidate",
        "video_metadata",
        "knowledge_job",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"
    conn.close()


def test_bookmark_newest_first(db):
    """Bookmarks ordered by captured_at DESC should return newest first."""
    _insert_account(db)
    _insert_principal(db)

    # Insert 3 bookmarks with different timestamps
    ts = [
        "2026-07-16T10:00:00",
        "2026-07-16T12:00:00",
        "2026-07-16T11:00:00",
    ]
    for i, t in enumerate(ts):
        db.execute(
            """INSERT INTO bookmark
               (app_account_id, telegram_update_id, telegram_user_id,
                captured_at, received_at, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("acc-1", f"upd-{i}", "12345", t, t, 3),
        )
    db.commit()

    rows = db.execute(
        "SELECT captured_at FROM bookmark WHERE app_account_id=? "
        "ORDER BY captured_at DESC, id DESC",
        ("acc-1",),
    ).fetchall()

    times = [r["captured_at"] for r in rows]
    assert times == sorted(times, reverse=True), f"Not newest-first: {times}"


def test_duplicate_update_id_raises(db):
    """Duplicate (app_account_id, telegram_update_id) should raise IntegrityError."""
    _insert_account(db)
    _insert_principal(db)

    db.execute(
        """INSERT INTO bookmark
           (app_account_id, telegram_update_id, telegram_user_id,
            captured_at, received_at, priority)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("acc-1", "upd-1", "12345", "2026-07-16T10:00:00", "2026-07-16T10:00:00", 3),
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO bookmark
               (app_account_id, telegram_update_id, telegram_user_id,
                captured_at, received_at, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("acc-1", "upd-1", "12345", "2026-07-16T10:00:00", "2026-07-16T10:00:00", 3),
        )
        db.commit()


def test_priority_out_of_range_raises(db):
    """priority=6 should raise IntegrityError (CHECK constraint)."""
    _insert_account(db)
    _insert_principal(db)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO bookmark
               (app_account_id, telegram_update_id, telegram_user_id,
                captured_at, received_at, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("acc-1", "upd-x", "12345", "2026-07-16T10:00:00", "2026-07-16T10:00:00", 6),
        )
        db.commit()


def test_invalid_source_state_raises(db):
    """An invalid source_state should raise IntegrityError."""
    _insert_account(db)
    _insert_principal(db)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO bookmark
               (app_account_id, telegram_update_id, telegram_user_id,
                captured_at, received_at, priority, source_state)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("acc-1", "upd-y", "12345", "2026-07-16T10:00:00", "2026-07-16T10:00:00", 3, "bogus_state"),
        )
        db.commit()


def test_fk_enforcement_missing_account(db):
    """Inserting a bookmark with non-existent app_account_id should fail."""
    _insert_principal(db)

    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """INSERT INTO bookmark
               (app_account_id, telegram_update_id, telegram_user_id,
                captured_at, received_at, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("nonexistent-account", "upd-z", "12345", "2026-07-16T10:00:00", "2026-07-16T10:00:00", 3),
        )
        db.commit()


def test_migration_idempotent(db):
    """Running migrate() twice should not re-apply migrations."""
    mig_dir = Path(__file__).resolve().parent.parent.parent / "migrations"
    migrate(db, mig_dir)  # second time
    rows = db.execute("SELECT COUNT(*) as c FROM schema_version").fetchone()
    assert rows["c"] == 1  # only one migration applied once
