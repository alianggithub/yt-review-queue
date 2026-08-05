-- 001_initial.sql — YouTube Review Queue schema
-- Creates all 9 tables from DESIGN-v2.md §8.1

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Migration tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    filename    TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 1. Application account
CREATE TABLE IF NOT EXISTS app_account (
    id          TEXT PRIMARY KEY,   -- UUID
    display_name TEXT NOT NULL,
    timezone    TEXT DEFAULT 'UTC',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    disabled_at TEXT
);

-- 2. Telegram principal (whitelist)
CREATE TABLE IF NOT EXISTS telegram_principal (
    telegram_user_id  TEXT PRIMARY KEY,  -- numeric Telegram ID as text
    display_name      TEXT,
    active            INTEGER NOT NULL DEFAULT 1,  -- 1=active, 0=disabled
    first_seen_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tp_active ON telegram_principal(active);

-- 3. Membership (Telegram user → application account)
CREATE TABLE IF NOT EXISTS account_membership (
    app_account_id    TEXT NOT NULL REFERENCES app_account(id),
    telegram_user_id  TEXT NOT NULL REFERENCES telegram_principal(telegram_user_id),
    role              TEXT NOT NULL DEFAULT 'member'
                     CHECK (role IN ('owner', 'member', 'viewer')),
    is_default        INTEGER NOT NULL DEFAULT 0,  -- 1=default account for this user
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (app_account_id, telegram_user_id)
);

-- 4. Google connection (OAuth enrollment)
CREATE TABLE IF NOT EXISTS google_connection (
    id                                TEXT PRIMARY KEY,   -- UUID
    app_account_id                    TEXT NOT NULL REFERENCES app_account(id),
    youtube_channel_id                TEXT,
    youtube_channel_title             TEXT,
    data_portability_credential_ref   TEXT,   -- path to var/credentials/<label>_dp.json
    youtube_data_credential_ref       TEXT,   -- path to var/credentials/<label>_yt.json
    grant_expires_at                  TEXT,   -- ISO 8601 UTC
    last_export_at                    TEXT,
    last_success_at                   TEXT,
    created_at                        TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gc_account ON google_connection(app_account_id);

-- 5. Bookmark (the core capture record)
CREATE TABLE IF NOT EXISTS bookmark (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    app_account_id      TEXT NOT NULL REFERENCES app_account(id),
    telegram_update_id  TEXT NOT NULL,
    telegram_user_id    TEXT NOT NULL REFERENCES telegram_principal(telegram_user_id),
    captured_at         TEXT NOT NULL,   -- Telegram message.date, UTC IS8601
    received_at         TEXT NOT NULL,   -- server receipt time, UTC IS8601
    priority            INTEGER NOT NULL CHECK (priority BETWEEN 0 AND 5),
    note                TEXT,
    source_state        TEXT NOT NULL DEFAULT 'awaiting_history'
                        CHECK (source_state IN (
                            'awaiting_history', 'candidate',
                            'resolved_estimated', 'resolved_exact',
                            'ambiguous', 'expired'
                        )),
    watch_state         TEXT NOT NULL DEFAULT 'queued'
                        CHECK (watch_state IN ('queued', 'dismissed', 'watched')),
    selected_match_id   INTEGER,        -- FK to match_candidate.id, nullable
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (app_account_id, telegram_update_id)
);
CREATE INDEX IF NOT EXISTS idx_bm_account ON bookmark(app_account_id);
CREATE INDEX IF NOT EXISTS idx_bm_account_captured ON bookmark(app_account_id, captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_bm_source_state ON bookmark(source_state);
CREATE INDEX IF NOT EXISTS idx_bm_watch_state ON bookmark(watch_state);

-- 6. Activity event (normalized from Data Portability or Takeout)
CREATE TABLE IF NOT EXISTS activity_event (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    google_connection_id    TEXT NOT NULL REFERENCES google_connection(id),
    source                  TEXT NOT NULL CHECK (source IN ('data_portability', 'takeout')),
    source_event_key        TEXT NOT NULL,   -- stable hash(connection_id, video_id, time)
    activity_at            TEXT NOT NULL,    -- UTC ISO8601
    video_id                TEXT,
    title                   TEXT,
    channel_name            TEXT,
    raw_payload_hash        TEXT,            -- for audit/debug
    created_at             TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (source_event_key)
);
CREATE INDEX IF NOT EXISTS idx_ae_connection_time ON activity_event(google_connection_id, activity_at DESC);
CREATE INDEX IF NOT EXISTS idx_ae_video ON activity_event(video_id);

-- 7. Match candidate
CREATE TABLE IF NOT EXISTS match_candidate (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmark_id         INTEGER NOT NULL REFERENCES bookmark(id),
    activity_event_id   INTEGER NOT NULL REFERENCES activity_event(id),
    estimated_offset_s  INTEGER,    -- nullable; null if unknown
    offset_accuracy     TEXT NOT NULL DEFAULT 'unknown'
                        CHECK (offset_accuracy IN ('unknown', 'estimated', 'exact')),
    confidence          REAL NOT NULL DEFAULT 0.0,   -- 0.0–1.0
    confidence_version  TEXT NOT NULL DEFAULT 'v1-weighted',
    reason_json         TEXT,    -- JSON string with timing diffs and signals
    selected_at         TEXT,
    selected_by         TEXT,    -- 'auto' or 'user' or null
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (bookmark_id, activity_event_id)
);
CREATE INDEX IF NOT EXISTS idx_mc_bookmark ON match_candidate(bookmark_id);
-- FK to bookmark.selected_match_id is deferred (circular); handled in app layer.
CREATE INDEX IF NOT EXISTS idx_mc_selected ON match_candidate(bookmark_id) WHERE selected_at IS NOT NULL;

-- 8. Video metadata (cache from YouTube Data API)
CREATE TABLE IF NOT EXISTS video_metadata (
    video_id        TEXT PRIMARY KEY,
    title           TEXT,
    channel_id      TEXT,
    channel_title   TEXT,
    duration_s      INTEGER,   -- nullable if unavailable
    fetched_at      TEXT NOT NULL DEFAULT (datetime('now')),
    fetch_status    TEXT NOT NULL DEFAULT 'ok'
                    CHECK (fetch_status IN ('ok', 'not_found', 'private', 'error'))
);

-- 9. Knowledge job (classification + wiki generation)
CREATE TABLE IF NOT EXISTS knowledge_job (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmark_id                 INTEGER NOT NULL REFERENCES bookmark(id),
    kb_category                 TEXT,
    classification_confidence   REAL,
    wiki_state                  TEXT NOT NULL DEFAULT 'not_requested'
                                CHECK (wiki_state IN ('not_requested', 'queued', 'generated', 'failed')),
    wiki_requested_at           TEXT,
    wiki_generated_at           TEXT,
    article_path                TEXT,
    content_hash                TEXT,
    error_code                  TEXT,
    last_attempt_at             TEXT,
    attempt_count               INTEGER NOT NULL DEFAULT 0,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (bookmark_id, content_hash)   -- idempotency: same content → same job
);
CREATE INDEX IF NOT EXISTS idx_kj_bookmark ON knowledge_job(bookmark_id);
CREATE INDEX IF NOT EXISTS idx_kj_state ON knowledge_job(wiki_state);
