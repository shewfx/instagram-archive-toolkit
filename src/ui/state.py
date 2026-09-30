"""The one background saver worker, shared by every browser tab of the UI."""

import threading
from collections import deque

from src import config, services
from src.instagram.saver import SaveStats
from src.instagram.saver import _hms as hms  # noqa: F401  (re-exported for the pages)

# Stop reasons that are a normal end rather than a warning/error.
_CLEAN_ENDS = ("Done.", "Stopped on request.")


class SaverWorker:
    """Runs services.save_session in one background thread, never two at once.

    The NiceGUI event loop never blocks: it only reads `state`, `stats` and `lines`, which the
    thread updates. Each Reel's outcome is committed by the save loop itself, so closing or
    reloading the page loses nothing. state: idle | running | stopping | stopped (warning/error).
    """

    def __init__(self, session=services.save_session):
        self._session = session
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.state = "idle"
        self.message = ""
        self.stats: SaveStats | None = None
        self.limit: int | None = None
        self.lines: deque[str] = deque(maxlen=5000)
        # Lines ever appended; a viewer compares it with its own count to find new lines.
        self.line_count = 0

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, limit: int | None) -> bool:
        """Start saving up to `limit` Reels (None: all). False if a run is already active."""
        with self._lock:
            if self.busy:
                return False
            self._stop.clear()
            self.limit, self.stats = limit, SaveStats()
            self.state, self.message = "running", ""
            self._thread = threading.Thread(target=self._run, name="saver", daemon=True)
            self._thread.start()
            return True

    def stop(self) -> None:
        """Finish the current Reel, then stop. Nothing is interrupted mid-Reel."""
        if self.busy:
            self._stop.set()
            self.state = "stopping"

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def _echo(self, line: str) -> None:
        self.lines.append(line)
        self.line_count += 1

    def _run(self) -> None:
        try:
            stats = self._session(
                self.limit, echo=self._echo, stats=self.stats, should_stop=self._stop.is_set
            )
            self.message = stats.stop_reason
        # Whatever goes wrong, the worker must end in a visible state, never stuck on running.
        except Exception as e:  # noqa: BLE001  e.g. Chrome failed to start, profile in use
            self.message = f"STOPPED: {type(e).__name__}: {str(e).splitlines()[0]}"
            self._echo(self.message)
        self.stats.finish()  # the save loop may never have run, e.g. Chrome failed to start
        self.state = "idle" if self.message.startswith(_CLEAN_ENDS) else "stopped"


def metrics(stats: SaveStats, pending: int, limit: int | None) -> dict:
    """Live numbers for the dashboard. pending is the current count in the database."""
    elapsed = stats.elapsed()  # frozen once the run has finished
    avg = stats.seconds_per_reel()
    remaining = pending if limit is None else max(min(pending, limit - stats.processed), 0)
    return {
        "elapsed": elapsed,
        "avg": avg,
        "per_hour": 3600 / avg if avg else 0.0,
        "remaining": remaining,
        "eta": remaining * avg,
    }


def percent_done(counts: dict) -> float:
    """Share of Reels that need no more work: saved, unavailable or skipped."""
    done = counts["saved"] + counts["unavailable"] + counts["skipped"]
    return done / counts["total"] if counts["total"] else 0.0


# The single worker for this process.
worker = SaverWorker()
BATCH_CHOICES = (10, 25, 50)


def batch_options() -> dict:
    """Saver batch choices; the configured BATCH_SIZE is always offered."""
    sizes = sorted({*BATCH_CHOICES, config.BATCH_SIZE})
    return {**{n: f"Process {n}" for n in sizes}, 0: "Process all"}
