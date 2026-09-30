import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent

# Both paths are gitignored. Never commit them.
PROFILE_DIR = ROOT / "browser-profile"
DB_PATH = ROOT / "data" / "reels.db"
# Reels parsed from Instagram's data export by `parse-export`.
EXPORT_PATH = ROOT / "data" / "liked_reels_export.json"
# parse-export keeps Reels liked at or after this moment: 2025-01-01 00:00 UTC.
EXPORT_SINCE = datetime(2025, 1, 1, tzinfo=ZoneInfo("UTC"))
# All liked / saved posts and Reels with their metadata, written by `build-search`.
LIKED_POSTS_PATH = ROOT / "data" / "liked_posts_export.json"
SAVED_POSTS_PATH = ROOT / "data" / "saved_posts_export.json"
# The export's liked_posts.html / saved_posts.html, used by the UI to rebuild the search index.
LIKED_HTML: Path | None = None
SAVED_HTML: Path | None = None

# Uses the locally installed Google Chrome rather than Playwright's bundled Chromium.
BROWSER_CHANNEL = "chrome"

LIKES_URL = "https://www.instagram.com/your_activity/interactions/likes/"

# Pacing. This runs against a real account: favour reliability over speed.
# Seconds between scrolls of the likes grid.
SCROLL_DELAY = 3.0
# Seconds to pause after opening each liked item, before returning to the grid.
ITEM_DELAY = 5.0
# The Settings page may raise ITEM_DELAY but never lower it below this.
MIN_ITEM_DELAY = ITEM_DELAY
# Seconds between a Reel's page loading and clicking Save.
ACTION_DELAY = 2.0
# Seconds to wait for a page or item to open before treating it as failed.
NAV_TIMEOUT = 20
# Stop after this many scrolls in a row that reveal nothing new.
MAX_IDLE_SCROLLS = 4

# `save` prints a progress summary every this many Reels.
PROGRESS_EVERY = 25
# Default batch preselected in the UI's saver controls.
BATCH_SIZE = 25
# `save` writes a log file per run here (gitignored, like all of data/).
LOG_DIR = ROOT / "data" / "logs"

# Stopping rules.
# Default for --stop-after-known: consecutive already-known Reels that end a repeat scan.
STOP_AFTER_KNOWN = 10
# Consecutive failed items that end the scan. Never retried automatically.
MAX_CONSECUTIVE_ERRORS = 3

# Local overrides edited on the UI's Settings page. Gitignored like all of data/; the CLI reads
# them too, so both always agree. Holds paths and pacing only, never cookies or session data.
SETTINGS_PATH = ROOT / "data" / "settings.json"


def _path(value):
    return Path(value) if str(value or "").strip() else None


def _item_delay(value):
    delay = float(value)
    if not MIN_ITEM_DELAY <= delay <= 600:  # also rejects nan
        raise ValueError(f"ITEM_DELAY must be {MIN_ITEM_DELAY} to 600 seconds")
    return delay


def _batch_size(value):
    size = int(value)
    if size < 1:
        raise ValueError("BATCH_SIZE must be 1 or more")
    return size


def _required_path(value):
    if not _path(value):
        raise ValueError("path must not be empty")
    return Path(value)


EDITABLE = {
    "LIKED_HTML": _path,
    "SAVED_HTML": _path,
    "DB_PATH": _required_path,
    "PROFILE_DIR": _required_path,
    "ITEM_DELAY": _item_delay,
    "BATCH_SIZE": _batch_size,
}


def current_settings() -> dict:
    return {
        k: (str(v) if isinstance(v, Path) else v) for k, v in globals().items() if k in EDITABLE
    }


def apply_settings(values: dict) -> None:
    """Validate all of `values` first, then apply them. Raises ValueError, changing nothing."""
    unknown = set(values) - set(EDITABLE)
    if unknown:
        raise ValueError(f"unknown settings: {sorted(unknown)}")
    parsed = {k: EDITABLE[k](v) for k, v in values.items()}
    globals().update(parsed)


def save_settings(values: dict) -> None:
    apply_settings(values)
    SETTINGS_PATH.parent.mkdir(exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(current_settings(), indent=2), encoding="utf-8")


if SETTINGS_PATH.exists():
    apply_settings(json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
