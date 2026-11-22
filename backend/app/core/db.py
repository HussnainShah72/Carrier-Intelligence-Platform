"""
SQLite persistence layer.

A single-file database keeps the project runnable on any laptop with zero setup.
Connections are per-thread (FastAPI runs blocking work in a threadpool), JSON
columns hold the structured NLP payloads, and `init_db()` is idempotent so the
schema is created on first boot and carried forward safely.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from app.core.config import settings
from app.core.logging_setup import get_logger

log = get_logger(__name__)

_local = threading.local()

SCHEMA_VERSION = 4

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ----------------------------------------------------------------- CV module
CREATE TABLE IF NOT EXISTS cv_documents (
    id              TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    file_type       TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    sha256          TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    char_count      INTEGER NOT NULL,
    extractor       TEXT NOT NULL,
    profile_json    TEXT NOT NULL,
    parse_warnings  TEXT NOT NULL DEFAULT '[]',
    parse_mode      TEXT NOT NULL DEFAULT 'hybrid',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cv_created ON cv_documents(created_at DESC);

-- ------------------------------------------------------------- role analysis
CREATE TABLE IF NOT EXISTS role_analyses (
    id                TEXT PRIMARY KEY,
    role_title        TEXT NOT NULL,
    role_slug         TEXT NOT NULL,
    location          TEXT NOT NULL DEFAULT '',
    seniority         TEXT NOT NULL DEFAULT 'any',
    requirements_json TEXT NOT NULL,
    scrape_json       TEXT NOT NULL,
    llm_json          TEXT NOT NULL,
    source_summary    TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_role_created ON role_analyses(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_role_slug ON role_analyses(role_slug);

CREATE TABLE IF NOT EXISTS job_postings (
    id               TEXT PRIMARY KEY,
    role_analysis_id TEXT NOT NULL,
    source           TEXT NOT NULL,
    source_type      TEXT NOT NULL,
    title            TEXT NOT NULL,
    company          TEXT NOT NULL DEFAULT '',
    location         TEXT NOT NULL DEFAULT '',
    url              TEXT NOT NULL DEFAULT '',
    posted_at        TEXT NOT NULL DEFAULT '',
    description      TEXT NOT NULL DEFAULT '',
    skills_json      TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT NOT NULL,
    FOREIGN KEY (role_analysis_id) REFERENCES role_analyses(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_posting_role ON job_postings(role_analysis_id);

-- --------------------------------------------------------------- gap analysis
CREATE TABLE IF NOT EXISTS gap_analyses (
    id               TEXT PRIMARY KEY,
    cv_id            TEXT NOT NULL,
    role_analysis_id TEXT NOT NULL,
    result_json      TEXT NOT NULL,
    match_percent    REAL NOT NULL,
    created_at       TEXT NOT NULL,
    FOREIGN KEY (cv_id) REFERENCES cv_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (role_analysis_id) REFERENCES role_analyses(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_gap_created ON gap_analyses(created_at DESC);

-- ------------------------------------------------------------ CV improvement
CREATE TABLE IF NOT EXISTS bullet_improvements (
    id            TEXT PRIMARY KEY,
    cv_id         TEXT NOT NULL DEFAULT '',
    role_title    TEXT NOT NULL DEFAULT '',
    original      TEXT NOT NULL,
    improved      TEXT NOT NULL,
    explanation   TEXT NOT NULL DEFAULT '',
    changes_json  TEXT NOT NULL DEFAULT '[]',
    flags_json    TEXT NOT NULL DEFAULT '[]',
    decision      TEXT NOT NULL DEFAULT 'pending',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bullet_cv ON bullet_improvements(cv_id);

-- ---------------------------------------------------------------- interviews
CREATE TABLE IF NOT EXISTS interviews (
    id            TEXT PRIMARY KEY,
    cv_id         TEXT NOT NULL DEFAULT '',
    role_title    TEXT NOT NULL,
    difficulty    TEXT NOT NULL DEFAULT 'medium',
    mode          TEXT NOT NULL DEFAULT 'voice',
    stage         TEXT NOT NULL DEFAULT 'introduction',
    status        TEXT NOT NULL DEFAULT 'active',
    plan_json     TEXT NOT NULL DEFAULT '{}',
    state_json    TEXT NOT NULL DEFAULT '{}',
    report_json   TEXT NOT NULL DEFAULT '',
    started_at    TEXT NOT NULL,
    ended_at      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_interview_started ON interviews(started_at DESC);

CREATE TABLE IF NOT EXISTS interview_turns (
    id            TEXT PRIMARY KEY,
    interview_id  TEXT NOT NULL,
    turn_index    INTEGER NOT NULL,
    speaker       TEXT NOT NULL,
    stage         TEXT NOT NULL,
    text          TEXT NOT NULL,
    meta_json     TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL,
    FOREIGN KEY (interview_id) REFERENCES interviews(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_turn_interview ON interview_turns(interview_id, turn_index);

-- ------------------------------------------------------- performance metrics
CREATE TABLE IF NOT EXISTS latency_events (
    id                 TEXT PRIMARY KEY,
    interview_id       TEXT NOT NULL DEFAULT '',
    turn_index         INTEGER NOT NULL DEFAULT -1,
    role_title         TEXT NOT NULL DEFAULT '',
    stt_ms             REAL,
    llm_total_ms       REAL,
    llm_ttft_ms        REAL,
    tts_first_ms       REAL,
    tts_total_ms       REAL,
    e2e_first_audio_ms REAL,
    total_ms           REAL,
    audio_seconds      REAL,
    chars_out          INTEGER,
    stt_engine         TEXT NOT NULL DEFAULT '',
    tts_engine         TEXT NOT NULL DEFAULT '',
    llm_provider       TEXT NOT NULL DEFAULT '',
    llm_model          TEXT NOT NULL DEFAULT '',
    mode               TEXT NOT NULL DEFAULT 'voice',
    created_at         TEXT NOT NULL,
    speech_end_to_server_ms REAL,
    e2e_from_speech_end_ms  REAL
);
CREATE INDEX IF NOT EXISTS idx_latency_interview ON latency_events(interview_id);
CREATE INDEX IF NOT EXISTS idx_latency_created ON latency_events(created_at DESC);

-- --------------------------------------------------------------- activity log
CREATE TABLE IF NOT EXISTS activity_log (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    ref_id      TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_log(created_at DESC);
"""

_RESETTABLE_TABLES = (
    "latency_events",
    "interview_turns",
    "interviews",
    "bullet_improvements",
    "gap_analyses",
    "job_postings",
    "role_analyses",
    "cv_documents",
    "activity_log",
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex[:16]
    return f"{prefix}_{raw}" if prefix else raw


def get_connection() -> sqlite3.Connection:
    """Return this thread's connection, creating it on first use."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        settings.database_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(settings.database_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _local.conn = conn
    return conn


def init_db() -> None:
    """Create the schema if needed.  Safe to call on every boot."""
    conn = get_connection()
    conn.executescript(SCHEMA)
    # v4: browser-side end-of-speech timings. Added to existing databases in
    # place, so an upgrade keeps every earlier measurement.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(latency_events)")}
    for column in ("speech_end_to_server_ms", "e2e_from_speech_end_ms"):
        if column not in existing:
            conn.execute(f"ALTER TABLE latency_events ADD COLUMN {column} REAL")
    conn.execute(
        "INSERT INTO schema_meta(key, value) VALUES('version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()
    log.info("Database ready at %s (schema v%s)", settings.database_path, SCHEMA_VERSION)


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    conn = get_connection()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


def query_all(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return list(get_connection().execute(sql, tuple(params)).fetchall())


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return get_connection().execute(sql, tuple(params)).fetchone()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        log.warning("Could not decode stored JSON column; returning default")
        return default


def log_activity(kind: str, title: str, detail: str = "", ref_id: str = "") -> None:
    execute(
        "INSERT INTO activity_log(id, kind, title, detail, ref_id, created_at) VALUES(?,?,?,?,?,?)",
        (new_id("act"), kind, title[:200], detail[:400], ref_id, utcnow()),
    )


def reset_database() -> None:
    """Delete every row (used by Settings -> storage management, and by tests)."""
    conn = get_connection()
    for table in _RESETTABLE_TABLES:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    conn.execute("VACUUM")
    log.info("Database cleared on user request")


def storage_stats() -> dict[str, Any]:
    counts: dict[str, int] = {}
    for table in _RESETTABLE_TABLES:
        row = query_one(f"SELECT COUNT(*) AS c FROM {table}")
        counts[table] = int(row["c"]) if row else 0
    size = settings.database_path.stat().st_size if settings.database_path.exists() else 0
    return {"path": str(settings.database_path), "size_bytes": size, "row_counts": counts}
