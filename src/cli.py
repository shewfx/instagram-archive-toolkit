import argparse
import json
import sys
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from src import config, database
from src.instagram.urls import parse_post_url, post_url


def open_context(p):
    config.PROFILE_DIR.mkdir(exist_ok=True)
    return p.chromium.launch_persistent_context(
        config.PROFILE_DIR, channel=config.BROWSER_CHANNEL, headless=False, no_viewport=True
    )


def cmd_login(args):
    with sync_playwright() as p:
        ctx = open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.instagram.com/accounts/login/")
        print("Log in to Instagram in the browser window, then close the window.")
        ctx.wait_for_event("close", timeout=0)
    print("Browser closed. Session saved to", config.PROFILE_DIR)


def cmd_scan(args):
    from src.instagram.likes_scanner import scan

    conn = database.connect(config.DB_PATH)
    # Read once; the scan compares each shortcode against this string in memory.
    cutoff = database.get_setting(conn, database.HISTORICAL_CUTOFF)
    if cutoff:
        print(f"Historical cutoff: {cutoff} (scan stops after storing it)")
    try:
        with sync_playwright() as p:
            ctx = open_context(p)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                stats = scan(page, conn, args.limit, args.stop_after_known, cutoff=cutoff)
            finally:
                with suppress(PlaywrightError):  # browser may already be gone after Ctrl+C
                    ctx.close()
    finally:
        conn.close()
    print(f"\n{stats.stop_reason}")
    print(f"\nLiked items inspected: {stats.inspected}")
    print(f"Reels found: {stats.reels}")
    print(f"New Reels added: {stats.new}")
    print(f"Already known: {stats.known}")
    print(f"Errors: {stats.errors}")


def cmd_status(args):
    conn = database.connect(config.DB_PATH)
    c = database.status_counts(conn)
    cutoff = database.get_setting(conn, database.HISTORICAL_CUTOFF)
    conn.close()
    print(f"Total discovered: {c['total']}")
    print(f"Pending: {c['pending']}")
    print(f"Saved: {c['saved']}")
    print(f"Failed: {c['failed']}")
    print(f"Unavailable: {c['unavailable']}")
    print(f"Historical cutoff: {cutoff or 'not set'}")


def cmd_set_cutoff(args):
    if not parse_post_url(f"/p/{args.shortcode}/"):
        raise SystemExit(f"Not a valid shortcode: {args.shortcode!r}")
    conn = database.connect(config.DB_PATH)
    database.set_setting(conn, database.HISTORICAL_CUTOFF, args.shortcode)
    conn.close()
    print(f"Historical cutoff set to {args.shortcode}")


def cmd_list_pending(args):
    conn = database.connect(config.DB_PATH)
    rows = database.list_pending(conn)
    conn.close()
    for r in rows:
        print(f"{r['discovered_at']}  {r['reel_url']}")
    print(f"\n{len(rows)} pending")


def cmd_parse_export(args):
    from src.instagram.export import build_manifest

    html = Path(args.html).read_text(encoding="utf-8")
    manifest, stats = build_manifest(html, config.EXPORT_SINCE)
    config.EXPORT_PATH.parent.mkdir(exist_ok=True)
    config.EXPORT_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Liked entries parsed: {stats['parsed']}")
    print(f"Reel entries: {stats['reels']}")
    print(f"Reels since {config.EXPORT_SINCE:%Y-%m-%d %H:%M %Z}: {stats['since']}")
    print(f"Duplicates removed: {stats['duplicates']}")
    if manifest:
        print(f"Oldest liked_at: {manifest[-1]['liked_at']}")
        print(f"Newest liked_at: {manifest[0]['liked_at']}")
    print(f"\nWrote {len(manifest)} Reels to {config.EXPORT_PATH}")


def cmd_import_export(args):
    manifest = json.loads(config.EXPORT_PATH.read_text(encoding="utf-8"))
    conn = database.connect(config.DB_PATH)
    before = database.status_counts(conn)["total"]
    new = database.import_reels(
        conn, [(r["shortcode"], post_url(r["shortcode"]), r["liked_at"]) for r in manifest]
    )
    total = database.status_counts(conn)["total"]
    conn.close()
    print(f"Reels in manifest: {len(manifest)}")
    print(f"Already in the database: {len(manifest) - new}")
    print(f"New Reels added as pending: {new}")
    print(f"Unique Reels in the database: {before} -> {total}")


SEARCH_MANIFESTS = {"liked": config.LIKED_POSTS_PATH, "saved": config.SAVED_POSTS_PATH}


def cmd_build_search(args):
    from src.instagram.export import parse_posts

    if not (args.liked or args.saved):
        raise SystemExit("Give --liked and/or --saved.")
    for source, html_path in (("liked", args.liked), ("saved", args.saved)):
        if not html_path:
            continue
        records = parse_posts(Path(html_path).read_text(encoding="utf-8"), source)
        out = SEARCH_MANIFESTS[source]
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
        reels = sum(r["post_type"] == "reel" for r in records)
        print(f"{source}: {len(records)} posts ({reels} Reels) -> {out}")


def search(sources, query):
    """Print matches from the given manifests, newest first. Returns the matches."""
    from src.instagram.export import search_posts, snippet

    # Captions carry emoji and non-Latin text; a redirected Windows console would choke on them.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    records = []
    for source in sources:
        path = SEARCH_MANIFESTS[source]
        if not path.exists():
            raise SystemExit(f"{path} not found. Run build-search --{source} <{source}_posts.html>")
        records += json.loads(path.read_text(encoding="utf-8"))
    hits = search_posts(records, query)
    for r in hits:
        when = datetime.fromisoformat(r["timestamp"]).astimezone()
        print(f"[{r['source'].upper()}] {when:%Y-%m-%d %H:%M}  {r['url']}")
        owner = " ".join(
            filter(
                None,
                [r["username"] and "@" + r["username"], r["owner_name"] and f"({r['owner_name']})"],
            )
        )
        if owner:
            print(f"    {owner}")
        if r["caption"]:
            print(f"    {snippet(r['caption'], query)}")
        print()
    print(f"{len(hits)} result{'s' * (len(hits) != 1)} for {query!r}")
    return hits


def _local_now():
    return datetime.now(timezone.utc).astimezone()


def cmd_save(args):
    from src.instagram.saver import save

    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = config.LOG_DIR / f"save-{_local_now():%Y%m%d-%H%M%S}.log"
    with open(log_path, "a", encoding="utf-8") as log_file:

        def log(msg=""):
            line = f"{_local_now():%Y-%m-%d %H:%M:%S}  {msg}"
            print(line, flush=True)
            log_file.write(line + "\n")
            log_file.flush()

        conn = database.connect(config.DB_PATH)
        mode = "DRY RUN: nothing is clicked or stored. " if args.dry_run else ""
        scope = "all pending Reels" if args.all else f"up to {args.limit} Reels"
        pending = database.status_counts(conn)["pending"]
        log(f"{mode}Saving {scope}, oldest like first. Pending: {pending}. Log: {log_path}")
        try:
            with sync_playwright() as p:
                ctx = open_context(p)
                try:
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    stats = save(page, conn, args.limit, args.dry_run, log=log)
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


def positive_int(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return n


def non_negative_int(value):
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be 0 or more")
    return n


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m src.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="open the browser so you can log in manually").set_defaults(
        func=cmd_login
    )
    scan = sub.add_parser("scan", help="discover liked Reels and store them")
    scan.add_argument("--limit", type=positive_int, help="stop after this many Reels")
    scan.add_argument(
        "--stop-after-known",
        type=non_negative_int,
        default=config.STOP_AFTER_KNOWN,
        metavar="N",
        help=f"stop after N already-known Reels in a row; 0 disables "
        f"(default {config.STOP_AFTER_KNOWN})",
    )
    scan.set_defaults(func=cmd_scan)
    cut = sub.add_parser("set-cutoff", help="oldest Reel to import; scans stop after storing it")
    cut.add_argument("shortcode")
    cut.set_defaults(func=cmd_set_cutoff)
    export = sub.add_parser(
        "parse-export", help="read liked_posts.html from an Instagram data export (offline)"
    )
    export.add_argument("html", help="path to your_instagram_activity/likes/liked_posts.html")
    export.set_defaults(func=cmd_parse_export)
    sub.add_parser(
        "import-export", help="add Reels from data/liked_reels_export.json to the database"
    ).set_defaults(func=cmd_import_export)
    save = sub.add_parser("save", help="save pending Reels to Saved, oldest like first")
    how_many = save.add_mutually_exclusive_group(required=True)
    how_many.add_argument("--limit", type=positive_int, help="stop after this many Reels")
    how_many.add_argument(
        "--all", action="store_true", help="keep going until no pending Reels are left"
    )
    save.add_argument(
        "--dry-run",
        action="store_true",
        help="open each Reel and report its Save state; click nothing, store nothing",
    )
    save.set_defaults(func=cmd_save)
    build = sub.add_parser(
        "build-search", help="index liked/saved posts from an Instagram data export (offline)"
    )
    build.add_argument("--liked", metavar="HTML", help="path to likes/liked_posts.html")
    build.add_argument("--saved", metavar="HTML", help="path to saved/saved_posts.html")
    build.set_defaults(func=cmd_build_search)
    for name, sources in (
        ("search-liked", ["liked"]),
        ("search-saved", ["saved"]),
        ("search-all", ["liked", "saved"]),
    ):
        s = sub.add_parser(
            name, help=f"search {' and '.join(sources)} posts by caption, hashtag or owner"
        )
        s.add_argument("query", help='keyword or phrase, e.g. "harry potter"')
        s.set_defaults(func=lambda args, sources=sources: search(sources, args.query))
    sub.add_parser("status", help="show counts by status").set_defaults(func=cmd_status)
    sub.add_parser("list-pending", help="list Reels not yet processed").set_defaults(
        func=cmd_list_pending
    )
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
