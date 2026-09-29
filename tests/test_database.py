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
