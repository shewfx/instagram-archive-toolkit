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
)
"""


def connect(path) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


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
