"""SQLite database initialization and migration runner."""
from __future__ import annotations

import sqlite3
from pathlib import Path

# Directory containing migration .sql files, relative to this package
_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


def init_db(path: str | Path = "var/queue.sqlite3") -> sqlite3.Connection:
    """Open a SQLite connection in WAL mode with foreign keys enabled,
    run any pending migrations, and return the connection."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection, migrations_dir: Path | None = None) -> None:
    """Read .sql files from migrations_dir in order, run any not yet applied,
    and record them in the schema_version table."""
    mdir = migrations_dir or _MIGRATIONS_DIR
    if not mdir.is_dir():
        return

    # Ensure schema_version table exists (migration 0 bootstrap)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            filename    TEXT NOT NULL,
            applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    # Find all .sql files, sorted
    sql_files = sorted(mdir.glob("*.sql"))
    if not sql_files:
        return

    for sql_file in sql_files:
        # Derive version number from filename (e.g. "001_initial.sql" -> 1)
        try:
            version = int(sql_file.stem.split("_")[0])
        except (ValueError, IndexError):
            continue

        # Check if already applied
        row = conn.execute(
            "SELECT version FROM schema_version WHERE version = ?", (version,)
        ).fetchone()
        if row is not None:
            continue

        # Read and execute the migration
        sql = sql_file.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version (version, filename) VALUES (?, ?)",
            (version, sql_file.name),
        )
        conn.commit()
