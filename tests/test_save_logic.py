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


def test_should_stop_ends_between_reels_and_stats_are_live(conn):
    from src.instagram.saver import SaveStats

    stats, seen_current = SaveStats(), []

    def save_one(code):
        seen_current.append(stats.current)
        return "saved"

    rows = database.pending_to_save(conn)
    result = run(
        rows,
        conn,
        save_one,
        log=lambda _m: None,
        stats=stats,
        should_stop=lambda: stats.processed >= 2,
    )
    assert result is stats
    assert seen_current == ["A", "B"]
    assert stats.current is None
    assert stats.stop_reason == "Stopped on request. Progress is saved."
    assert statuses(conn) == {"A": "saved", "B": "saved", "C": "pending", "D": "pending"}


class FakePage:
    """Just enough of a Page for `saver`: it records the response listener."""

    def on(self, event, callback):
        assert event == "response"
        self.respond = lambda status: callback(type("R", (), {"status": status, "url": "u"}))


@pytest.fixture
def fake_browser(monkeypatch):
    """Patch the Playwright steps; `script` maps shortcode -> (status codes seen, state/exception)."""
    from src.instagram import saver as saver_mod

    monkeypatch.setattr(config, "ITEM_DELAY", 0)
    monkeypatch.setattr(config, "ACTION_DELAY", 0)
    page, script, opened = FakePage(), {}, []

    def open_reel(_page, code):
        opened.append(code)
        statuses_seen, result = script.get(code, ((), "unsaved"))
        for status in statuses_seen:
            page.respond(status)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(saver_mod, "open_reel", open_reel)
    monkeypatch.setattr(saver_mod, "click_save", lambda _page: None)
    return saver_mod, page, script, opened


def run_saver(conn, fake_browser):
    saver_mod, page, _script, _opened = fake_browser
    return run(
        database.pending_to_save(conn), conn, saver_mod.saver(page, False), log=lambda _m: None
    )


def test_http_429_after_a_confirmed_save_records_it_then_stops(conn, fake_browser):
    _, _, script, opened = fake_browser
    script["B"] = ((429,), "unsaved")
    stats = run_saver(conn, fake_browser)
    assert opened == ["A", "B"]
    assert "HTTP 429" in stats.stop_reason and stats.stop_reason.startswith("STOPPED")
    assert statuses(conn) == {"A": "saved", "B": "saved", "C": "pending", "D": "pending"}


def test_http_429_with_a_failing_reel_leaves_it_pending(conn, fake_browser):
    _, _, script, opened = fake_browser
    script["A"] = ((200, 429), ValueError("no Save button appeared"))
    stats = run_saver(conn, fake_browser)
    assert opened == ["A"]
    assert "HTTP 429" in stats.stop_reason and stats.errors == 0
    assert set(statuses(conn).values()) == {"pending"}


def test_http_429_never_marks_unavailable(conn, fake_browser):
    _, _, script, _ = fake_browser
    script["A"] = ((429,), "unavailable")
    stats = run_saver(conn, fake_browser)
    assert "HTTP 429" in stats.stop_reason
    assert statuses(conn)["A"] == "pending"


def test_other_statuses_do_not_stop(conn, fake_browser):
    _, _, script, opened = fake_browser
    script["A"] = ((404, 500), "unsaved")
    stats = run_saver(conn, fake_browser)
    assert stats.stop_reason == "Done." and opened == ["A", "B", "C", "D"]


class FakeClock:
    """Stands in for the saver module's `time`: monotonic() is whatever the test sets."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    from src.instagram import saver as saver_mod

    c = FakeClock()
    monkeypatch.setattr(saver_mod, "time", c)
    return c


def timed_run(conn, clock, save_one, **kw):
    """Run with stats started on the fake clock; each Reel takes 10 fake seconds."""
    from src.instagram.saver import SaveStats

    stats = SaveStats(started=clock.now)

    def ten_seconds_each(code):
        clock.now += 10
        return save_one(code)

    rows = database.pending_to_save(conn)
    run(rows, conn, ten_seconds_each, log=lambda _m: None, stats=stats, **kw)
    return stats


def assert_frozen(stats, clock):
    before = (stats.elapsed(), stats.seconds_per_reel(), stats.summary(0))
    clock.now += 3600  # an hour later, e.g. the dashboard still refreshing
    assert (stats.elapsed(), stats.seconds_per_reel(), stats.summary(0)) == before


def test_elapsed_increases_while_running(clock):
    from src.instagram.saver import SaveStats

    stats = SaveStats(started=clock.now, processed=2)
    clock.now += 5
    assert stats.elapsed() == 5 and stats.seconds_per_reel() == 2.5
    clock.now += 5
    assert stats.elapsed() == 10 and stats.finished is None


def test_elapsed_freezes_after_normal_completion(conn, clock):
    stats = timed_run(conn, clock, lambda _c: "saved")
    assert stats.stop_reason == "Done."
    assert stats.elapsed() == 40 and stats.seconds_per_reel() == 10
    assert_frozen(stats, clock)


def test_elapsed_freezes_after_safe_stop(conn, clock):
    stats = timed_run(conn, clock, lambda _c: "saved", should_stop=lambda: clock.now >= 1020)
    assert stats.stop_reason.startswith("Stopped on request")
    assert stats.elapsed() == 20
    assert_frozen(stats, clock)


def test_elapsed_freezes_after_http_429(conn, clock, fake_browser):
    from src.instagram.saver import SaveStats

    saver_mod, page, script, _ = fake_browser
    script["B"] = ((429,), ValueError("no Save button appeared"))
    stats = SaveStats(started=clock.now)
    save_one = saver_mod.saver(page, False)

    def ten_seconds_each(code):
        clock.now += 10
        return save_one(code)

    run(database.pending_to_save(conn), conn, ten_seconds_each, log=lambda _m: None, stats=stats)
    assert "HTTP 429" in stats.stop_reason
    assert stats.elapsed() == 20
    assert_frozen(stats, clock)


@pytest.mark.parametrize(
    "stop",
    [
        Blocked("login page."),
        Blocked("challenge page."),
        Blocked("Instagram showed a warning while saving."),
        PlaywrightError("Target page, context or browser has been closed"),
    ],
)
def test_elapsed_freezes_after_warnings_and_errors(conn, clock, stop):
    def save_one(code):
        if code == "B":
            raise stop
        return "saved"

    stats = timed_run(conn, clock, save_one)
    assert stats.stop_reason.startswith("STOPPED")
    assert stats.elapsed() == 20
    assert_frozen(stats, clock)
