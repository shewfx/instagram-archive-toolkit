"""Tests for the save loop, run against a real SQLite file.

No browser is involved: `run` only sees what save_one returns or raises, exactly as the Playwright
layer provides it. Reels are liked A (oldest) to D (newest), so they are processed A, B, C, D.
"""

import pytest
from playwright.sync_api import Error as PlaywrightError

from src import config, database
from src.cli import main
from src.instagram.likes_scanner import Blocked
from src.instagram.saver import run


@pytest.fixture
def conn(tmp_path):
    c = database.connect(tmp_path / "reels.db")
    database.import_reels(
        c, [(code, "u", f"2025-0{i + 1}-01T00:00:00+00:00") for i, code in enumerate("ABCD")]
    )
    yield c
    c.close()


def statuses(conn):
    return {r["shortcode"]: r["status"] for r in conn.execute("SELECT * FROM reels")}


def save(conn, results, limit=None, dry_run=False, log=lambda _m: None, **kw):
    """results maps shortcode -> outcome, or an exception to raise."""
    seen = []

    def save_one(code):
        seen.append(code)
        r = results[code]
        if isinstance(r, BaseException):
            raise r
        return r

    stats = run(database.pending_to_save(conn, limit), conn, save_one, dry_run, log=log, **kw)
    stats.seen = seen
    return stats


def test_progress_summary_every_n_reels(conn):
    lines = []
    save(conn, dict.fromkeys("ABCD", "saved"), log=lines.append, progress_every=2)
    progress = [line for line in lines if line.startswith("-- ")]
    assert len(progress) == 2
    assert progress[0].startswith("-- 2 processed | newly saved 2 | already saved 0 |")
    assert "| failed 0 | pending 2 |" in progress[0]
    assert "| pending 0 |" in progress[1]


def test_browser_gone_stops_without_blaming_the_reel(conn):
    closed = PlaywrightError("Target page, context or browser has been closed")
    stats = save(conn, {"A": "saved", "B": closed, "C": "saved"})
    assert stats.stop_reason.startswith("STOPPED: Chrome/Playwright stopped working")
    assert stats.errors == 0
    assert statuses(conn) == {"A": "saved", "B": "pending", "C": "pending", "D": "pending"}


def test_timeout_is_a_normal_failure(conn):
    stats = save(conn, {"A": PlaywrightError("Timeout 20000ms exceeded."), "B": "saved"}, limit=2)
    assert stats.errors == 1 and stats.stop_reason == "Done."
    assert statuses(conn)["A"] == "failed"


@pytest.mark.parametrize("argv", [["save"], ["save", "--all", "--limit", "5"]])
def test_save_needs_exactly_one_of_limit_or_all(argv):
    with pytest.raises(SystemExit):
        main(argv)


def test_outcomes_are_stored_per_reel_oldest_first(conn):
    results = {"A": "saved", "B": "already_saved", "C": "unavailable", "D": "saved"}
    stats = save(conn, results)
    assert stats.seen == ["A", "B", "C", "D"]
    assert stats.stop_reason == "Done."
    assert statuses(conn) == {"A": "saved", "B": "saved", "C": "unavailable", "D": "saved"}
    assert stats.outcomes == {"saved": 2, "already_saved": 1, "unavailable": 1, "would_save": 0}
    assert conn.execute("SELECT COUNT(*) FROM reels WHERE processed_at IS NULL").fetchone()[0] == 0


def test_limit_then_rerun_continues_with_remaining_pending(conn):
    save(conn, dict.fromkeys("ABCD", "saved"), limit=2)
    assert statuses(conn) == {"A": "saved", "B": "saved", "C": "pending", "D": "pending"}
    stats = save(conn, dict.fromkeys("ABCD", "saved"))
    assert stats.seen == ["C", "D"]
    assert set(statuses(conn).values()) == {"saved"}


def test_crash_mid_run_keeps_everything_already_saved(conn):
    stats = save(conn, {"A": "saved", "B": "saved", "C": KeyboardInterrupt(), "D": "saved"})
    assert stats.stop_reason == "Interrupted. Progress is saved."
    assert statuses(conn) == {"A": "saved", "B": "saved", "C": "pending", "D": "pending"}


def test_blocked_stops_immediately_and_leaves_reel_pending(conn):
    stats = save(conn, {"A": "saved", "B": Blocked("challenge page."), "C": "saved"})
    assert stats.stop_reason.startswith("STOPPED: challenge page.")
    assert stats.seen == ["A", "B"]
    assert statuses(conn) == {"A": "saved", "B": "pending", "C": "pending", "D": "pending"}


def test_failed_reel_is_recorded_and_run_continues(conn):
    results = {"A": ValueError("no Save button appeared"), "B": "saved", "C": "saved", "D": "saved"}
    stats = save(conn, results)
    assert stats.errors == 1
    row = conn.execute("SELECT * FROM reels WHERE shortcode = 'A'").fetchone()
    assert (row["status"], row["last_error"]) == ("failed", "no Save button appeared")
    assert statuses(conn)["D"] == "saved"


def test_consecutive_errors_stop_the_run(conn):
    n = config.MAX_CONSECUTIVE_ERRORS
    assert n < 4
    stats = save(conn, dict.fromkeys("ABCD", ValueError("x")))
    assert stats.processed == n
    assert "failed in a row" in stats.stop_reason


def test_dry_run_stores_nothing(conn):
    results = {"A": "would_save", "B": "already_saved", "C": "unavailable", "D": ValueError("x")}
    stats = save(conn, results, dry_run=True)
    assert stats.processed == 4
    assert set(statuses(conn).values()) == {"pending"}
    assert conn.execute("SELECT MAX(attempts) FROM reels").fetchone()[0] == 0
