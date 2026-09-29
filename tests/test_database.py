import pytest

from src import database


@pytest.fixture
def conn(tmp_path):
    c = database.connect(tmp_path / "reels.db")
    yield c
    c.close()


def test_new_reel_is_pending_with_defaults(conn):
    assert database.add_reel(conn, "ABC", "https://www.instagram.com/reel/ABC/") is True
    row = conn.execute("SELECT * FROM reels").fetchone()
    assert row["status"] == "pending"
    assert row["attempts"] == 0
    assert row["discovered_at"]
    assert row["last_error"] is None and row["processed_at"] is None


def test_duplicate_shortcode_is_ignored(conn):
    assert database.add_reel(conn, "ABC", "https://www.instagram.com/reel/ABC/") is True
    assert database.add_reel(conn, "ABC", "https://www.instagram.com/reel/ABC/?x=1") is False
    assert conn.execute("SELECT COUNT(*) FROM reels").fetchone()[0] == 1


def test_existing_data_survives_reconnect(tmp_path):
    path = tmp_path / "reels.db"
    c = database.connect(path)
    database.add_reel(c, "ABC", "u")
    c.execute("UPDATE reels SET status = 'saved'")
    c.commit()
    c.close()

    c = database.connect(path)
    assert database.add_reel(c, "ABC", "u") is False
    assert database.status_counts(c)["saved"] == 1
    c.close()


def test_status_counts(conn):
    assert database.status_counts(conn) == {
        "pending": 0,
        "saved": 0,
        "failed": 0,
        "unavailable": 0,
        "total": 0,
    }
    for code in ["A", "B", "C", "D"]:
        database.add_reel(conn, code, "u")
    conn.execute("UPDATE reels SET status = 'saved' WHERE shortcode = 'A'")
    conn.execute("UPDATE reels SET status = 'failed' WHERE shortcode = 'B'")
    counts = database.status_counts(conn)
    assert counts == {"pending": 2, "saved": 1, "failed": 1, "unavailable": 0, "total": 4}


def test_list_pending_only_returns_pending_in_discovery_order(conn):
    for code in ["A", "B", "C"]:
        database.add_reel(conn, code, "u")
    conn.execute("UPDATE reels SET status = 'saved' WHERE shortcode = 'B'")
    assert [r["shortcode"] for r in database.list_pending(conn)] == ["A", "C"]


def test_invalid_status_rejected(conn):
    import sqlite3

    database.add_reel(conn, "A", "u")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE reels SET status = 'bogus'")


def test_settings_roundtrip_and_overwrite(tmp_path):
    path = tmp_path / "reels.db"
    c = database.connect(path)
    assert database.get_setting(c, database.HISTORICAL_CUTOFF) is None
    database.set_setting(c, database.HISTORICAL_CUTOFF, "OLD")
    database.set_setting(c, database.HISTORICAL_CUTOFF, "NEWCODE")
    c.close()

    c = database.connect(path)
    assert database.get_setting(c, database.HISTORICAL_CUTOFF) == "NEWCODE"
    c.close()


def test_connect_upgrades_existing_db_without_losing_reels(tmp_path):
    import sqlite3

    path = tmp_path / "reels.db"
    old = sqlite3.connect(path)
    old.execute(database.SCHEMA.split(";")[0])  # reels table only, like a Phase 1 database
    old.execute("INSERT INTO reels (shortcode, reel_url) VALUES ('A', 'u')")
    old.commit()
    old.close()

    c = database.connect(path)
    assert database.status_counts(c)["total"] == 1
    assert database.get_setting(c, database.HISTORICAL_CUTOFF) is None
    c.close()


PHASE1_REELS = """
CREATE TABLE reels (
    id            INTEGER PRIMARY KEY,
    shortcode     TEXT NOT NULL UNIQUE,
    reel_url      TEXT NOT NULL,
    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'saved', 'failed', 'unavailable')),
    attempts      INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT,
    processed_at  TEXT
)"""


def test_phase1_db_is_upgraded_keeping_rows_and_settings(tmp_path):
    import sqlite3

    path = tmp_path / "reels.db"
    old = sqlite3.connect(path)
    old.execute(PHASE1_REELS)
    old.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    old.execute("INSERT INTO settings VALUES ('historical_cutoff_shortcode', 'CUT')")
    old.execute(
        "INSERT INTO reels (shortcode, reel_url, status, attempts) VALUES ('A', 'u', 'saved', 2)"
    )
    old.execute("INSERT INTO reels (shortcode, reel_url) VALUES ('B', 'v')")
    old.commit()
    old.close()

    c = database.connect(path)
    rows = [
        dict(r) for r in c.execute("SELECT id, shortcode, status, attempts, liked_at FROM reels")
    ]
    assert rows == [
        {"id": 1, "shortcode": "A", "status": "saved", "attempts": 2, "liked_at": None},
        {"id": 2, "shortcode": "B", "status": "pending", "attempts": 0, "liked_at": None},
    ]
    assert database.get_setting(c, database.HISTORICAL_CUTOFF) == "CUT"
    database.import_reels(c, [("B", "v", "2025-01-01T00:00:00+00:00")])
    assert c.execute("SELECT liked_at FROM reels WHERE shortcode = 'B'").fetchone()[0]
    c.close()


def test_import_adds_new_as_pending_and_keeps_known_status(conn):
    database.add_reel(conn, "KNOWN", "https://www.instagram.com/p/KNOWN/")
    conn.execute("UPDATE reels SET status = 'saved' WHERE shortcode = 'KNOWN'")
    rows = [
        ("NEW", "https://www.instagram.com/p/NEW/", "2025-02-01T00:00:00+00:00"),
        ("KNOWN", "https://www.instagram.com/p/OTHER/", "2025-03-01T00:00:00+00:00"),
    ]
    assert database.import_reels(conn, rows) == 1
    assert database.import_reels(conn, rows) == 0
    got = {r["shortcode"]: dict(r) for r in conn.execute("SELECT * FROM reels")}
    assert got["NEW"]["status"] == "pending"
    assert got["NEW"]["liked_at"] == "2025-02-01T00:00:00+00:00"
    assert got["KNOWN"]["status"] == "saved"
    assert got["KNOWN"]["reel_url"] == "https://www.instagram.com/p/KNOWN/"
    assert got["KNOWN"]["liked_at"] == "2025-03-01T00:00:00+00:00"


def test_pending_to_save_is_oldest_like_first_by_liked_at(conn):
    for code in ["SCAN_NEWEST", "SCAN_OLDER"]:  # likes-page scan: newest first, no liked_at
        database.add_reel(conn, code, "u")
    # Insertion order deliberately differs from liked_at order.
    database.import_reels(
        conn,
        [
            ("EXP_NEW", "u", "2026-01-01T00:00:00+00:00"),
            ("EXP_OLDEST", "u", "2025-01-01T00:00:00+00:00"),
            ("EXP_MID", "u", "2025-06-01T00:00:00+00:00"),
            ("EXP_DONE", "u", "2024-12-31T18:00:00+00:00"),
        ],
    )
    database.mark(conn, "EXP_DONE", "saved")
    codes = [r["shortcode"] for r in database.pending_to_save(conn)]
    assert codes == ["EXP_OLDEST", "EXP_MID", "EXP_NEW", "SCAN_OLDER", "SCAN_NEWEST"]
    assert [r["shortcode"] for r in database.pending_to_save(conn, limit=2)] == [
        "EXP_OLDEST",
        "EXP_MID",
    ]


def test_mark_records_status_time_and_attempt(conn):
    from datetime import datetime

    database.add_reel(conn, "A", "u")
    database.mark(conn, "A", "failed", "no Save button appeared")
    row = conn.execute("SELECT * FROM reels").fetchone()
    assert (row["status"], row["attempts"]) == ("failed", 1)
    assert row["last_error"] == "no Save button appeared"
    assert datetime.fromisoformat(row["processed_at"]).utcoffset().total_seconds() == 0
