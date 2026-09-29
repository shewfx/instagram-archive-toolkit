from datetime import datetime, timezone

from src import config
from src.instagram.export import _ENTRY, build_manifest, parse_liked_posts


def entry(url, liked_at):
    # Mirrors the export: the entry's link, then an Owner block with its own link, then the date.
    return (
        f'<div class="pam _3-95 _2ph- _a6-g {_ENTRY}'
        f'<a target="_blank" href="{url}">{url}</a>'
        f'<div class="_a6-p"><a target="_blank" href="https://www.instagram.com/reel/OWNER/">o</a>'
        f'</div></div><div class="_3-94 _a6-o">{liked_at}</div></div>'
    )


def reel(code, liked_at):
    return entry(f"https://www.instagram.com/reel/{code}/", liked_at)


def test_pacific_times_become_utc_in_export_order():
    html = entry("https://www.instagram.com/p/A/", "Sep 28, 2026 2:46 am") + reel(
        "B", "Dec 31, 2024 11:53 am"
    )
    assert parse_liked_posts(html) == [
        # PDT, UTC-7
        ("https://www.instagram.com/p/A/", datetime(2026, 9, 28, 9, 46, tzinfo=timezone.utc)),
        # PST, UTC-8
        ("https://www.instagram.com/reel/B/", datetime(2024, 12, 31, 19, 53, tzinfo=timezone.utc)),
    ]


def test_cutoff_is_midnight_utc():
    assert config.EXPORT_SINCE == datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    html = "".join(
        [
            reel("AT", "Dec 31, 2024 4:00 pm"),  # PST, UTC-8: exactly 2025-01-01 00:00 UTC
            reel("BEFORE", "Dec 31, 2024 3:59 pm"),  # one minute earlier
        ]
    )
    manifest, _ = build_manifest(html, config.EXPORT_SINCE)
    assert [r["shortcode"] for r in manifest] == ["AT"]
    assert manifest[0]["liked_at"] == "2025-01-01T00:00:00+00:00"


def test_manifest_keeps_recent_reels_once_in_export_order():
    html = "".join(
        [
            reel("AAA", "Sep 28, 2026 2:46 am"),
            entry("https://www.instagram.com/p/PPP/", "Sep 27, 2026 1:00 pm"),
            entry("https://www.instagram.com/reels/audio/123456789/", "Sep 27, 2026 1:00 pm"),
            reel("AAA", "Sep 26, 2026 1:00 pm"),
            reel("B-b_1", "Jan 1, 2025 12:00 am"),
            reel("OLD", "Dec 30, 2024 11:53 pm"),
        ]
    )
    manifest, stats = build_manifest(html, config.EXPORT_SINCE)
    assert [r["shortcode"] for r in manifest] == ["AAA", "B-b_1"]
    assert manifest[0] == {
        "shortcode": "AAA",
        "url": "https://www.instagram.com/reel/AAA/",
        "type": "reel",
        "liked_at": "2026-09-28T09:46:00+00:00",
    }
    assert stats == {"parsed": 6, "reels": 4, "since": 3, "duplicates": 1}
