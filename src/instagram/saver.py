"""Phase 2: save pending Reels to Instagram's Saved (All posts) by opening each Reel's own page."""

import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from src import config, database
from src.instagram import selectors
from src.instagram.likes_scanner import Blocked, _unexpected
from src.instagram.urls import parse_post_url

# Outcome of one Reel -> status stored in SQLite. Nothing is stored in a dry run.
STATUS = {
    "saved": "saved",
    "already_saved": "saved",
    "unavailable": "unavailable",
    "would_save": None,
}


@dataclass
class SaveStats:
    processed: int = 0
    outcomes: dict = field(default_factory=lambda: dict.fromkeys(STATUS, 0))
    errors: int = 0
    error_streak: int = 0
    seconds: list = field(default_factory=list)
    stop_reason: str = ""


def run(
    reels: Iterable,
    conn,
    save_one: Callable[[str], str],
    dry_run: bool = False,
    log=print,
) -> SaveStats:
    """Core save loop, independent of the browser.

    save_one(shortcode) returns an outcome from STATUS, raises ValueError/PlaywrightError for a
    failed Reel, or Blocked to stop everything. Each outcome is committed before the next Reel.
    """
    stats = SaveStats()
    try:
        for row in reels:
            code = row["shortcode"]
            stats.processed += 1
            start = time.monotonic()
            try:
                outcome = save_one(code)
            except (PlaywrightError, ValueError) as e:
                msg = str(e).splitlines()[0]
                stats.errors += 1
                stats.error_streak += 1
                if not dry_run:
                    database.mark(conn, code, "failed", msg)
                log(f"[{stats.processed}] error  {code}  {msg}")
            else:
                stats.error_streak = 0
                stats.outcomes[outcome] += 1
                if STATUS[outcome] and not dry_run:
                    database.mark(conn, code, STATUS[outcome])
                log(f"[{stats.processed}] {outcome:<13} {code}")
            stats.seconds.append(time.monotonic() - start)
            if stats.error_streak >= config.MAX_CONSECUTIVE_ERRORS:
                stats.stop_reason = (
                    f"{stats.error_streak} Reels failed in a row. Instagram may be limiting "
                    "actions or its page changed. Progress is saved; try again later."
                )
                break
        else:
            stats.stop_reason = "Done."
    except Blocked as e:
        stats.stop_reason = f"STOPPED: {e} Progress is saved."
    except PlaywrightError as e:
        stats.stop_reason = f"STOPPED on browser error: {str(e).splitlines()[0]} Progress is saved."
    except KeyboardInterrupt:
        stats.stop_reason = "Interrupted. Progress is saved."
    return stats


def _timeout():
    return config.NAV_TIMEOUT * 1000


def _check_block(page: Page, what: str) -> None:
    """Called after an expected step failed: stop the run if Instagram shows a warning."""
    if page.get_by_text(re.compile(selectors.BLOCK_TEXT, re.IGNORECASE)).count():
        raise Blocked(f"Instagram showed a warning while {what}. Stop using the tool for a while.")


def open_reel(page: Page, shortcode: str) -> str:
    """Open the Reel's page and return its save state: "unsaved", "saved" or "unavailable"."""
    # /p/ rather than /reel/: /reel/<code>/ was seen redirecting to a different Reel (see urls.py).
    page.goto(f"https://www.instagram.com/p/{shortcode}/", timeout=_timeout())
    parsed = parse_post_url(page.url)
    if not parsed or parsed[1] != shortcode:
        raise _unexpected(page)
    unsaved, saved = page.locator(selectors.UNSAVED), page.locator(selectors.SAVED)
    gone = page.get_by_text(re.compile(selectors.UNAVAILABLE_TEXT, re.IGNORECASE))
    try:
        unsaved.or_(saved).or_(gone).first.wait_for(timeout=_timeout())
    except PlaywrightError:
        _check_block(page, "opening a Reel")
        raise ValueError("no Save button appeared") from None
    if gone.count():
        return "unavailable"
    return "saved" if saved.count() else "unsaved"


def click_save(page: Page) -> None:
    """Click Save once and wait until the control shows Remove.

    Instagram also opens its Collections popover; it is left alone and closes on the next page.
    """
    page.locator(selectors.UNSAVED).first.click(timeout=_timeout())
    try:
        page.locator(selectors.SAVED).first.wait_for(timeout=_timeout())
    except PlaywrightError:
        _check_block(page, "saving")
        raise ValueError("Save was clicked but the control never changed to Remove") from None


def saver(page: Page, dry_run: bool) -> Callable[[str], str]:
    """Build save_one(shortcode) for `run`, driving `page`."""

    def save_one(shortcode: str) -> str:
        state = open_reel(page, shortcode)
        if state == "unsaved":
            if dry_run:
                outcome = "would_save"
            else:
                time.sleep(config.ACTION_DELAY)
                click_save(page)
                outcome = "saved"
        else:
            # "saved" means the control already shows Remove. Never click it.
            outcome = "already_saved" if state == "saved" else state
        time.sleep(config.ITEM_DELAY)
        return outcome

    return save_one


def save(page: Page, conn, limit=None, dry_run=False, log=print) -> SaveStats:
    return run(database.pending_to_save(conn, limit), conn, saver(page, dry_run), dry_run, log)
