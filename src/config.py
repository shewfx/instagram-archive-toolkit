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

# Uses the locally installed Google Chrome rather than Playwright's bundled Chromium.
BROWSER_CHANNEL = "chrome"

LIKES_URL = "https://www.instagram.com/your_activity/interactions/likes/"

# Pacing. This runs against a real account: favour reliability over speed.
# Seconds between scrolls of the likes grid.
SCROLL_DELAY = 3.0
# Seconds to pause after opening each liked item, before returning to the grid.
ITEM_DELAY = 5.0
# Seconds between a Reel's page loading and clicking Save.
ACTION_DELAY = 2.0
# Seconds to wait for a page or item to open before treating it as failed.
NAV_TIMEOUT = 20
# Stop after this many scrolls in a row that reveal nothing new.
MAX_IDLE_SCROLLS = 4

# `save` prints a progress summary every this many Reels.
PROGRESS_EVERY = 25
# `save` writes a log file per run here (gitignored, like all of data/).
LOG_DIR = ROOT / "data" / "logs"

# Stopping rules.
# Default for --stop-after-known: consecutive already-known Reels that end a repeat scan.
STOP_AFTER_KNOWN = 10
# Consecutive failed items that end the scan. Never retried automatically.
MAX_CONSECUTIVE_ERRORS = 3
