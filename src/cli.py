import argparse
from contextlib import suppress

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from src import config, database


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
    try:
        with sync_playwright() as p:
            ctx = open_context(p)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                stats = scan(page, conn, args.limit, args.stop_after_known)
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
    conn.close()
    print(f"Total discovered: {c['total']}")
    print(f"Pending: {c['pending']}")
    print(f"Saved: {c['saved']}")
    print(f"Failed: {c['failed']}")
    print(f"Unavailable: {c['unavailable']}")


def cmd_list_pending(args):
    conn = database.connect(config.DB_PATH)
    rows = database.list_pending(conn)
    conn.close()
    for r in rows:
        print(f"{r['discovered_at']}  {r['reel_url']}")
    print(f"\n{len(rows)} pending")


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
    sub.add_parser("status", help="show counts by status").set_defaults(func=cmd_status)
    sub.add_parser("list-pending", help="list Reels not yet processed").set_defaults(
        func=cmd_list_pending
    )
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
