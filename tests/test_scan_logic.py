"""Tests for the scan loop's stopping rules, run against a real SQLite file.

Each tile is (aria_label, open_item). No browser is involved: `run` only sees labels and
whatever open_item returns or raises, exactly as the Playwright layer provides them.
"""

import pytest

from src import config, database
from src.instagram.likes_scanner import Blocked, run


@pytest.fixture
def conn(tmp_path):
    c = database.connect(tmp_path / "reels.db")
    yield c
    c.close()


def reel(code):
    return ("Video, 1 of 9, by @x, shared September 1, 2026", lambda: code)


def photo():
    return ("Photo, 1 of 9, by @x, shared September 1, 2026", lambda: pytest.fail("photo opened"))


def failing():
    def open_item():
        raise ValueError("item did not open")

    return ("Video, 1 of 9, by @x, shared September 1, 2026", open_item)


def blocked():
    def open_item():
        raise Blocked("challenge page.")

    return ("Video, 1 of 9, by @x, shared September 1, 2026", open_item)


def seed(conn, codes):
    for c in codes:
        database.add_reel(conn, c, "u")


def scan(conn, items, **kw):
    return run(iter(items), conn, log=lambda _msg: None, **kw)


def known_codes(n, prefix="K"):
    return [f"{prefix}{i}" for i in range(n)]


def test_stops_after_threshold_of_consecutive_known(conn):
    codes = known_codes(15)
    seed(conn, codes)
    stats = scan(conn, [reel(c) for c in codes], stop_after_known=10)
    assert stats.reels == 10
    assert stats.known == 10
    assert "10 already-known Reels in a row" in stats.stop_reason


def test_does_not_stop_one_short_of_threshold(conn):
    codes = known_codes(9)
    seed(conn, codes)
    stats = scan(conn, [reel(c) for c in codes], stop_after_known=10)
    assert stats.reels == 9
    assert stats.stop_reason == "Reached the end of the liked items."


def test_new_reel_resets_the_streak(conn):
    before, after = known_codes(9, "A"), known_codes(9, "B")
    seed(conn, before + after)
    items = [reel(c) for c in before] + [reel("NEW")] + [reel(c) for c in after]
    stats = scan(conn, items, stop_after_known=10)
    assert stats.new == 1
    assert stats.known == 18
    assert stats.stop_reason == "Reached the end of the liked items."


def test_zero_disables_early_stop(conn):
    codes = known_codes(30)
    seed(conn, codes)
    stats = scan(conn, [reel(c) for c in codes], stop_after_known=0)
    assert stats.reels == 30
    assert stats.stop_reason == "Reached the end of the liked items."


def test_photos_and_unknown_tiles_do_not_count_toward_streak(conn):
    codes = known_codes(9)
    seed(conn, codes)
    other = ("Carousel, 1 of 9, by @x", lambda: pytest.fail("unknown tile opened"))
    items = [reel(c) for c in codes] + [photo(), other, photo(), other]
    stats = scan(conn, items, stop_after_known=10)
    assert stats.inspected == 13
    assert stats.reels == 9
    assert stats.stop_reason == "Reached the end of the liked items."


def test_errors_do_not_count_toward_streak(conn):
    codes = known_codes(9)
    seed(conn, codes)
    items = [reel(c) for c in codes] + [failing(), failing()]
    stats = scan(conn, items, stop_after_known=10)
    assert stats.errors == 2
    assert stats.known_streak == 9
    assert stats.stop_reason == "Reached the end of the liked items."


def test_error_between_known_reels_does_not_reset_streak(conn):
    codes = known_codes(10)
    seed(conn, codes)
    items = [reel(c) for c in codes[:5]] + [failing()] + [reel(c) for c in codes[5:]]
    stats = scan(conn, items, stop_after_known=10)
    assert stats.known == 10
    assert "already-known" in stats.stop_reason


def test_limit_applies_before_higher_known_threshold(conn):
    codes = known_codes(20)
    seed(conn, codes)
    stats = scan(conn, [reel(c) for c in codes], limit=5, stop_after_known=10)
    assert stats.reels == 5
    assert stats.stop_reason == "Reached --limit 5."


def test_limit_counts_failed_reels_and_skips_photos(conn):
    items = [photo(), reel("A"), failing(), photo(), reel("B"), reel("C"), reel("D")]
    stats = scan(conn, items, limit=3)
    assert stats.reels == 3
    assert stats.inspected == 5
    assert database.status_counts(conn)["total"] == 2


def test_consecutive_errors_stop_the_scan_and_keep_progress(conn):
    n = config.MAX_CONSECUTIVE_ERRORS
    items = [reel("A")] + [failing()] * n + [reel("NEVER")]
    stats = scan(conn, items)
    assert stats.errors == n
    assert "failed in a row" in stats.stop_reason
    assert [r["shortcode"] for r in database.list_pending(conn)] == ["A"]


def test_blocked_stops_immediately_and_keeps_progress(conn):
    items = [reel("A"), reel("B"), blocked(), reel("NEVER")]
    stats = scan(conn, items)
    assert stats.stop_reason.startswith("STOPPED: challenge page.")
    assert stats.new == 2
    assert [r["shortcode"] for r in database.list_pending(conn)] == ["A", "B"]


def test_blocked_while_loading_the_grid_stops_cleanly(conn):
    def items():
        yield reel("A")
        raise Blocked("redirected to login.")

    stats = run(items(), conn, log=lambda _msg: None)
    assert stats.stop_reason.startswith("STOPPED: redirected to login.")
    assert database.status_counts(conn)["pending"] == 1
