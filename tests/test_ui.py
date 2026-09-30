"""The UI's saver worker and helpers, with a fake session instead of a browser."""

import threading

import pytest

from src import config
from src.instagram.saver import SaveStats
from src.ui.state import SaverWorker, batch_options, metrics, percent_done


class FakeSession:
    """Stands in for services.save_session: 'saves' Reels until told to stop or out of Reels."""

    def __init__(self, reels=3, reason="Done.", error=None):
        self.reels, self.reason, self.error = reels, reason, error
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def __call__(self, limit, echo, stats, should_stop):
        self.calls.append(limit)
        self.started.set()
        echo("starting")
        self.release.wait(5)
        if self.error:
            raise self.error
        for code in "ABCDEFG"[: self.reels]:
            if should_stop():
                stats.stop_reason = "Stopped on request. Progress is saved."
                return stats
            stats.current = code
            stats.processed += 1
            echo(f"saved {code}")
        stats.current = None
        stats.stop_reason = self.reason
        return stats


def run_to_end(worker, session, limit=None):
    assert worker.start(limit)
    session.started.wait(5)
    session.release.set()
    worker.join(5)


def test_only_one_worker_at_a_time():
    session = FakeSession()
    worker = SaverWorker(session)
    assert worker.start(10)
    session.started.wait(5)
    assert worker.busy and worker.state == "running"
    assert worker.start(10) is False  # a second start is refused
    session.release.set()
    worker.join(5)
    assert session.calls == [10]
    assert (worker.state, worker.message) == ("idle", "Done.")
    assert list(worker.lines) == ["starting", "saved A", "saved B", "saved C"]
    assert worker.line_count == 4
    assert worker.start(None)  # a new run may start once the last one ended
    worker.join(5)


def test_stop_is_graceful():
    session = FakeSession()
    worker = SaverWorker(session)
    worker.start(None)
    session.started.wait(5)
    worker.stop()
    assert worker.state == "stopping"
    session.release.set()
    worker.join(5)
    assert worker.stats.processed == 0
    assert worker.state == "idle" and worker.message.startswith("Stopped on request")


@pytest.mark.parametrize(
    "session",
    [
        FakeSession(reason="STOPPED: Instagram answered HTTP 429 (Too Many Requests)."),
        FakeSession(reason="3 Reels failed in a row. Instagram may be limiting actions"),
        FakeSession(error=RuntimeError("profile in use\nmore detail")),
    ],
)
def test_warnings_and_errors_leave_a_visible_stopped_state(session):
    worker = SaverWorker(session)
    run_to_end(worker, session)
    assert worker.state == "stopped"
    assert not worker.busy
    if session.error:
        assert worker.message == "STOPPED: RuntimeError: profile in use"
        assert worker.lines[-1] == worker.message


def test_metrics_for_a_limited_batch():
    stats = SaveStats(processed=10)
    stats.started -= 100  # 10 s per Reel
    m = metrics(stats, pending=500, limit=25)
    assert m["remaining"] == 15
    assert round(m["avg"]) == 10 and round(m["per_hour"]) == 360
    assert round(m["eta"]) == 150
    assert metrics(stats, pending=500, limit=None)["remaining"] == 500
    assert metrics(SaveStats(), pending=5, limit=None)["per_hour"] == 0


def test_percent_done_counts_finished_reels():
    counts = {"saved": 5, "unavailable": 1, "skipped": 2, "pending": 2, "failed": 0, "total": 10}
    assert percent_done(counts) == 0.8
    assert percent_done(dict.fromkeys(counts, 0)) == 0.0


def test_batch_options_always_offer_the_configured_size(monkeypatch):
    monkeypatch.setattr(config, "BATCH_SIZE", 40)
    assert list(batch_options()) == [10, 25, 40, 50, 0]


def test_every_page_is_registered():
    from nicegui import app

    import src.ui.app  # noqa: F401

    paths = {getattr(r, "path", None) for r in app.routes}
    assert {"/", "/search", "/failed", "/exports", "/settings", "/logs"} <= paths


def test_logs_page_reads_only_listed_files(tmp_path, monkeypatch):
    from src.ui.pages.logs import read_tail

    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(config, "LOG_DIR", logs)
    (logs / "save-1.log").write_text("a\nb\n", encoding="utf-8")
    (tmp_path / "secret.log").write_text("x", encoding="utf-8")
    assert read_tail("save-1.log") == "a\nb"
    with pytest.raises(ValueError):
        read_tail("../secret.log")


def test_tick_ruler_shows_done_then_failed_shares():
    from src.ui.components.widgets import ruler_html

    html = ruler_html(0.5, 0.1, ticks=20)
    assert html.count('class="tick') == 20
    assert html.count(" done") == 10 and html.count(" fail") == 2
    assert "left: calc(50.0000% - 1px)" in html
    # Any failure shows at least one red tick; none shows none.
    assert ruler_html(0.2, 0.001, ticks=20).count(" fail") == 1
    assert ruler_html(0.2, 0, ticks=20).count(" fail") == 0
    assert ruler_html(0, 0, ticks=20).count(" done") == 0


def test_dashboard_numbers_freeze_once_the_worker_stops(monkeypatch):
    from src.instagram import saver as saver_mod

    now = [1000.0]
    monkeypatch.setattr(
        saver_mod, "time", type("T", (), {"monotonic": staticmethod(lambda: now[0])})
    )

    def session(limit, echo, stats, should_stop):
        stats.started = now[0]
        now[0] += 30
        stats.processed = 3
        stats.stop_reason = "STOPPED: Instagram answered HTTP 429 (Too Many Requests)."
        stats.finish()
        return stats

    worker = SaverWorker(session)
    worker.start(None)
    worker.join(5)
    assert worker.state == "stopped"
    first = metrics(worker.stats, pending=100, limit=None)
    now[0] += 600
    assert metrics(worker.stats, pending=100, limit=None) == first
    assert first["elapsed"] == 30 and round(first["per_hour"]) == 360


def test_a_run_that_never_started_still_freezes():
    import time

    session = FakeSession(error=RuntimeError("Chrome failed to start"))
    worker = SaverWorker(session)
    run_to_end(worker, session)
    stats = worker.stats
    assert stats.finished is not None
    frozen = stats.elapsed()
    time.sleep(0.05)
    assert stats.elapsed() == frozen == stats.finished - stats.started
