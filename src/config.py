from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Both paths are gitignored. Never commit them.
PROFILE_DIR = ROOT / "browser-profile"
DB_PATH = ROOT / "data" / "reels.db"

# Uses the locally installed Google Chrome rather than Playwright's bundled Chromium.
BROWSER_CHANNEL = "chrome"

LIKES_URL = "https://www.instagram.com/your_activity/interactions/likes/"

# Pacing. This runs against a real account: favour reliability over speed.
# Seconds between scrolls of the likes grid.
SCROLL_DELAY = 3.0
# Seconds to pause after opening each liked item, before returning to the grid.
ITEM_DELAY = 5.0
# Seconds to wait for a page or item to open before treating it as failed.
NAV_TIMEOUT = 20
# Stop after this many scrolls in a row that reveal nothing new.
MAX_IDLE_SCROLLS = 4

# Stopping rules.
# Default for --stop-after-known: consecutive already-known Reels that end a repeat scan.
STOP_AFTER_KNOWN = 10
# Consecutive failed items that end the scan. Never retried automatically.
MAX_CONSECUTIVE_ERRORS = 3
