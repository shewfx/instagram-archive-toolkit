import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REELS_TABLE = """
CREATE TABLE IF NOT EXISTS reels (
    id            INTEGER PRIMARY KEY,
    shortcode     TEXT NOT NULL UNIQUE,
    reel_url      TEXT NOT NULL,
    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'saved', 'failed', 'unavailable', 'skipped')),
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    processed_at  TEXT,
    liked_at      TEXT
)"""

SCHEMA = f"""
{REELS_TABLE};
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

HISTORICAL_CUTOFF = "historical_cutoff_shortcode"
# skipped: set by hand (UI "Mark skipped") so the saver never retries it.
STATUSES = ("pending", "saved", "failed", "unavailable", "skipped")
_COLUMNS = (
    "id, shortcode, reel_url, discovered_at, status, attempts, last_error, processed_at, liked_at"
)


def connect(path) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if "liked_at" not in {r["name"] for r in conn.execute("PRAGMA table_info(reels)")}:
        conn.execute("ALTER TABLE reels ADD COLUMN liked_at TEXT")  # Phase 1 database
    table_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'reels'").fetchone()[0]
    if "'skipped'" not in table_sql:
        _rebuild_reels(conn)
    return conn


def _rebuild_reels(conn) -> None:
    """Recreate reels with the current CHECK constraint, keeping every row. All or nothing.

    SQLite cannot alter a CHECK in place. The explicit BEGIN matters: sqlite3 does not open a
    transaction for DDL by itself.
    """
    conn.execute("BEGIN")
    try:
        conn.execute("ALTER TABLE reels RENAME TO reels_old")
        conn.execute(REELS_TABLE)
        conn.execute(f"INSERT INTO reels ({_COLUMNS}) SELECT {_COLUMNS} FROM reels_old")
        conn.execute("DROP TABLE reels_old")
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


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


def import_reels(conn, reels: list[tuple[str, str, str]]) -> int:
    """Insert (shortcode, reel_url, liked_at) rows as pending. Returns how many were new.

    Known shortcodes keep their status, URL and history; they only gain a missing liked_at.
    """
    before = conn.total_changes
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO reels (shortcode, reel_url, liked_at) VALUES (?, ?, ?)", reels
        )
        new = conn.total_changes - before
        conn.executemany(
            "UPDATE reels SET liked_at = ? WHERE shortcode = ? AND liked_at IS NULL",
            [(liked_at, code) for code, _url, liked_at in reels],
        )
    return new


def status_counts(conn) -> dict:
    counts = dict.fromkeys(STATUSES, 0)
    for row in conn.execute("SELECT status, COUNT(*) FROM reels GROUP BY status"):
        counts[row[0]] = row[1]
    counts["total"] = sum(counts.values())
    return counts


def list_pending(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM reels WHERE status = 'pending' ORDER BY id").fetchall()


def pending_to_save(conn, limit: int | None = None) -> list[sqlite3.Row]:
    """Pending Reels, oldest like first, so Saved ends up newest-first like the likes page.

    Reels without liked_at came from the likes-page scan, which only reached the newest likes and
    stored them newest first: they go last, in reverse discovery order.
    """
    return conn.execute(
        "SELECT * FROM reels WHERE status = 'pending' "
        "ORDER BY liked_at IS NULL, liked_at, id DESC LIMIT ?",
        (-1 if limit is None else limit,),
    ).fetchall()


def mark(conn, shortcode: str, status: str, error: str | None = None) -> None:
    """Record the outcome of one save attempt. Committed immediately so a crash loses nothing."""
    with conn:
        conn.execute(
            "UPDATE reels SET status = ?, last_error = ?, attempts = attempts + 1, "
            "processed_at = ? WHERE shortcode = ?",
            (status, error, datetime.now(timezone.utc).isoformat(timespec="seconds"), shortcode),
        )


def list_failed(conn) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM reels WHERE status = 'failed' ORDER BY processed_at DESC, id"
    ).fetchall()


def set_status(conn, shortcode: str, status: str) -> None:
    """Change a Reel's status by hand, e.g. failed -> pending or skipped. Keeps its history."""
    with conn:
        conn.execute("UPDATE reels SET status = ? WHERE shortcode = ?", (status, shortcode))


def reset_failed(conn) -> int:
    """Put every failed Reel back to pending. Returns how many."""
    with conn:
        return conn.execute("UPDATE reels SET status = 'pending' WHERE status = 'failed'").rowcount
