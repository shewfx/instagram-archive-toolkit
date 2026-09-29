import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS reels (
    id            INTEGER PRIMARY KEY,
    shortcode     TEXT NOT NULL UNIQUE,
    reel_url      TEXT NOT NULL,
    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'saved', 'failed', 'unavailable')),
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    processed_at  TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

HISTORICAL_CUTOFF = "historical_cutoff_shortcode"


def connect(path) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def get_setting(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_setting(conn, key: str, value: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def add_reel(conn, shortcode: str, reel_url: str) -> bool:
    """Insert a reel. Returns True if new, False if it was already known."""
    with conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO reels (shortcode, reel_url) VALUES (?, ?)", (shortcode, reel_url)
        )
    return cur.rowcount == 1


def status_counts(conn) -> dict:
    counts = {"pending": 0, "saved": 0, "failed": 0, "unavailable": 0}
    for row in conn.execute("SELECT status, COUNT(*) FROM reels GROUP BY status"):
        counts[row[0]] = row[1]
    counts["total"] = sum(counts.values())
    return counts


def list_pending(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM reels WHERE status = 'pending' ORDER BY id").fetchall()
