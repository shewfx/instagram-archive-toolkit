import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from src import config, database
from src.instagram import selectors
from src.instagram.urls import parse_post_url, post_url


class Blocked(Exception):
    """Instagram showed a page the scanner does not expect: login, challenge, block, or new UI."""


@dataclass
class ScanStats:
    inspected: int = 0
    reels: int = 0
    new: int = 0
    known: int = 0
    errors: int = 0
    known_streak: int = 0
    error_streak: int = 0
    stop_reason: str = ""


def stop_reason(stats: ScanStats, limit: int | None, stop_after_known: int) -> str:
    if limit is not None and stats.reels >= limit:
        return f"Reached --limit {limit}."
    if stop_after_known and stats.known_streak >= stop_after_known:
        return (
            f"Found {stats.known_streak} already-known Reels in a row, so older likes were "
            "scanned before. Use --stop-after-known 0 to scan the full history."
        )
    if stats.error_streak >= config.MAX_CONSECUTIVE_ERRORS:
        return (
            f"{stats.error_streak} items failed in a row. Instagram may be limiting actions or "
            "its page changed. Progress is saved; try again later."
        )
    return ""


def run(
    items: Iterable[tuple[str | None, Callable[[], str]]],
    conn,
    limit: int | None = None,
    stop_after_known: int = config.STOP_AFTER_KNOWN,
    cutoff: str | None = None,
    log=print,
) -> ScanStats:
    """Core scan loop, independent of the browser.

    `items` yields (aria_label, open_item) per liked tile, newest first. open_item() returns the
    shortcode, raises ValueError/PlaywrightError for a failed item, or Blocked to stop everything.
    `cutoff` is the oldest Reel to import: it is stored normally, then the scan stops.
    """
    stats = ScanStats()
    try:
        for label, open_item in items:
            stats.inspected += 1
            if not selectors.is_video(label):
                continue
            stats.reels += 1
            try:
                shortcode = open_item()
            except (PlaywrightError, ValueError) as e:
                # Failures say nothing about whether older likes were scanned: known_streak untouched.
                stats.errors += 1
                stats.error_streak += 1
                log(f"[{stats.reels}] error  {str(e).splitlines()[0]}")
            else:
                stats.error_streak = 0
                if database.add_reel(conn, shortcode, post_url(shortcode)):
                    stats.new += 1
                    stats.known_streak = 0
                    log(f"[{stats.reels}] new    {shortcode}")
                else:
                    stats.known += 1
                    stats.known_streak += 1
                    log(f"[{stats.reels}] known  {shortcode}")
                if shortcode == cutoff:
                    stats.stop_reason = (
                        f"Reached the historical cutoff Reel {cutoff}. Nothing older was processed."
                    )
                    break
            stats.stop_reason = stop_reason(stats, limit, stop_after_known)
            if stats.stop_reason:
                break
        else:
            stats.stop_reason = "Reached the end of the liked items."
    except Blocked as e:
        stats.stop_reason = f"STOPPED: {e} Progress is saved."
    except PlaywrightError as e:
        stats.stop_reason = f"STOPPED on browser error: {str(e).splitlines()[0]} Progress is saved."
    except KeyboardInterrupt:
        stats.stop_reason = "Interrupted. Progress is saved."
    return stats


def _unexpected(page: Page) -> Blocked:
    return Blocked(
        f"Instagram showed an unexpected page ({page.url}). This may be a login prompt, a "
        "challenge/CAPTCHA, or an action block. Check the browser window. If it is a login "
        "page, run: python -m src.cli login"
    )


def open_likes(page: Page) -> None:
    page.goto(config.LIKES_URL, timeout=config.NAV_TIMEOUT * 1000)
    if not page.url.startswith(config.LIKES_URL):
        raise _unexpected(page)
    try:
        page.locator(selectors.LIKED_TILE).first.wait_for(timeout=config.NAV_TIMEOUT * 1000)
    except PlaywrightError:
        raise Blocked(
            "The likes page opened but no liked items appeared. Instagram may be showing a "
            "challenge or block, its layout may have changed, or there are no likes."
        ) from None


def load_tile(page: Page, index: int):
    """Scroll the grid until tile `index` exists. Returns None when the list runs out."""
    tiles = page.locator(selectors.LIKED_TILE)
    idle = 0
    while tiles.count() <= index:
        if idle >= config.MAX_IDLE_SCROLLS:
            return None
        before = tiles.count()
        tiles.first.evaluate(selectors.SCROLL_GRID_JS)
        try:
            page.wait_for_function(
                f"document.querySelectorAll({selectors.LIKED_TILE!r}).length > {before}",
                timeout=config.NAV_TIMEOUT * 1000,
            )
            idle = 0
        except PlaywrightError:
            idle += 1
        time.sleep(config.SCROLL_DELAY)
    return tiles.nth(index)


def open_tile(page: Page, tile) -> str:
    tile.click(timeout=config.NAV_TIMEOUT * 1000)
    try:
        page.wait_for_url(selectors.POST_URL_GLOB, timeout=config.NAV_TIMEOUT * 1000)
    except PlaywrightError:
        if not page.url.startswith(config.LIKES_URL):
            raise _unexpected(page) from None
        raise ValueError("item did not open (unavailable or deleted?)") from None
    parsed = parse_post_url(page.url)
    if not parsed:
        raise ValueError(f"unrecognised post URL: {page.url}")
    return parsed[1]


def liked_items(page: Page):
    """Yield (aria_label, open_item) for each liked tile, newest first."""
    open_likes(page)
    index = 0
    while True:
        if not page.url.startswith(config.LIKES_URL):
            # Leaving the grid resets it, so reopen and let load_tile scroll back down.
            # ponytail: O(n^2) scrolling for large histories; see README "Why it's slow".
            time.sleep(config.ITEM_DELAY)
            open_likes(page)
        tile = load_tile(page, index)
        if tile is None:
            return
        index += 1
        yield tile.get_attribute("aria-label"), lambda t=tile: open_tile(page, t)


def scan(
    page: Page, conn, limit=None, stop_after_known=config.STOP_AFTER_KNOWN, cutoff=None, log=print
):
    return run(
        liked_items(page), conn, limit, stop_after_known=stop_after_known, cutoff=cutoff, log=log
    )
