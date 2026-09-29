"""Parse liked_posts.html from Instagram's "Download your information" export. Fully offline."""

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from src.instagram.urls import parse_post_url

# The export writes entry times as US Pacific wall-clock time, whatever the account's location.
# Its header shows 2026-09-29T08:46Z as "01:46" (PDT, UTC-7); winter entries are PST, UTC-8.
EXPORT_TZ = ZoneInfo("America/Los_Angeles")

# Each top-level liked entry opens with this; nested boxes (e.g. Owner) use a plain class="_a6-p".
_ENTRY = 'uiBoxWhite noborder"><div class="_3-95 _a6-p">'
# The entry's own link comes first; links in the Owner block come after it.
_URL = re.compile(r'<a target="_blank" href="([^"]+)"')
_LIKED_AT = re.compile(r'class="_3-94 _a6-o">([^<]+)<')


def parse_liked_posts(html: str) -> list[tuple[str | None, datetime]]:
    """Return (url, liked_at) for every liked entry, in export order (newest first).

    liked_at is in UTC. The one repeated hour when Pacific time falls back in November is
    ambiguous in the export; it is read as the first (PDT) occurrence.
    """
    entries = []
    for chunk in html.split(_ENTRY)[1:]:
        url = _URL.search(chunk)
        text = _LIKED_AT.search(chunk).group(1)
        liked_at = datetime.strptime(text, "%b %d, %Y %I:%M %p").replace(tzinfo=EXPORT_TZ)
        entries.append((url and url.group(1), liked_at.astimezone(timezone.utc)))
    return entries


def build_manifest(html: str, since: datetime) -> tuple[list[dict], dict]:
    """Reels liked at or after `since`, deduplicated by shortcode, plus parse counts."""
    entries = parse_liked_posts(html)
    reels = []
    for url, liked_at in entries:
        parsed = parse_post_url(url)
        if parsed and parsed[0] == "reel":
            reels.append((parsed[1], url, liked_at))
    recent = [r for r in reels if r[2] >= since]
    manifest, seen = [], set()
    for shortcode, url, liked_at in recent:
        if shortcode not in seen:
            seen.add(shortcode)
            manifest.append(
                {
                    "shortcode": shortcode,
                    "url": url,
                    "type": "reel",
                    "liked_at": liked_at.isoformat(),
                }
            )
    stats = {
        "parsed": len(entries),
        "reels": len(reels),
        "since": len(recent),
        "duplicates": len(recent) - len(manifest),
    }
    return manifest, stats
