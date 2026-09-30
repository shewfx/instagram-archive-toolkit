"""Operations shared by the CLI and the UI, so both run the same code."""

import json
from contextlib import suppress
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from src import config, database


def local_now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def open_context(p):
    """The persistent Chrome profile that holds the Instagram login."""
    config.PROFILE_DIR.mkdir(exist_ok=True)
    return p.chromium.launch_persistent_context(
        config.PROFILE_DIR, channel=config.BROWSER_CHANNEL, headless=False, no_viewport=True
    )


def with_db(fn, *args):
    """fn(conn, *args) on a short-lived connection to the configured database."""
    conn = database.connect(config.DB_PATH)
    try:
        return fn(conn, *args)
    finally:
        conn.close()


def save_session(limit=None, dry_run=False, echo=print, **kw):
    """One `save` run: open Chrome, save pending Reels oldest like first, log to data/logs/.

    Every log line goes to a new log file and to echo(line). kw (`stats`, `should_stop`) is
    passed to the save loop. Returns its SaveStats.
    """
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    from src.instagram.saver import save

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = config.LOG_DIR / f"save-{local_now():%Y%m%d-%H%M%S}.log"
    with open(log_path, "a", encoding="utf-8") as log_file:

        def log(msg=""):
            line = f"{local_now():%Y-%m-%d %H:%M:%S}  {msg}"
            echo(line)
            log_file.write(line + "\n")
            log_file.flush()

        conn = database.connect(config.DB_PATH)
        mode = "DRY RUN: nothing is clicked or stored. " if dry_run else ""
        scope = "all pending Reels" if limit is None else f"up to {limit} Reels"
        pending = database.status_counts(conn)["pending"]
        log(f"{mode}Saving {scope}, oldest like first. Pending: {pending}. Log: {log_path}")
        try:
            with sync_playwright() as p:
                ctx = open_context(p)
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    stats = save(page, conn, limit, dry_run, log=log, **kw)
                finally:
                    with suppress(PlaywrightError):  # browser may already be gone after Ctrl+C
                        ctx.close()
            pending = database.status_counts(conn)["pending"]
        finally:
            conn.close()
        log(stats.stop_reason)
        log(f"Final: {stats.summary(pending)}")
        if stats.processed:
            log(f"Rate: {3600 / stats.seconds_per_reel():.0f} Reels/hour")
    return stats


# --- Search index: data/liked_posts_export.json, data/saved_posts_export.json ---


def manifest_paths() -> dict[str, Path]:
    return {"liked": config.LIKED_POSTS_PATH, "saved": config.SAVED_POSTS_PATH}


def build_index(source: str, html_path, out_path: Path) -> list[dict]:
    """Parse an export's liked_posts.html / saved_posts.html and write its search manifest."""
    from src.instagram.export import parse_posts

    records = parse_posts(Path(html_path).read_text(encoding="utf-8"), source)
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return records


@lru_cache(maxsize=4)
def _read_manifest(path: Path, _mtime: float) -> list[dict]:
    # Keyed on mtime, so a rebuilt index is re-read. Callers must not mutate the result.
    return json.loads(path.read_text(encoding="utf-8"))


def load_posts(paths: dict[str, Path], sources) -> list[dict]:
    """Records from the given sources' manifests. FileNotFoundError says how to build one."""
    records = []
    for source in sources:
        path = paths[source]
        if not path.exists():
            raise FileNotFoundError(
                f"{path} not found. Run build-search --{source} <{source}_posts.html>"
            )
        records += _read_manifest(path, path.stat().st_mtime)
    return records


def manifest_info(path: Path) -> dict | None:
    """Entry and Reel counts and build time of a manifest, or None if it was never built."""
    if not path.exists():
        return None
    records = _read_manifest(path, path.stat().st_mtime)
    return {
        "entries": len(records),
        "reels": sum(r["post_type"] == "reel" for r in records),
        "built_at": datetime.fromtimestamp(path.stat().st_mtime).astimezone(),
    }
