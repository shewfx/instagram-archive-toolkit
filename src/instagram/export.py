"""Parse liked_posts.html / saved_posts.html from Instagram's "Download your information" export.

Fully offline. Both files share the same entry layout.
"""

import html as htmllib
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
# Label/value rows: Caption on the entry, Name/Username inside the Owner block.
_ROW = '<td class="_a6_q">{}</td><td class="_2piu _a6_r">([^<]*)</td>'
_CAPTION = re.compile(_ROW.format("Caption"))
_NAME = re.compile(_ROW.format("Name"))
_USERNAME = re.compile(_ROW.format("Username"))
_HASHTAG = re.compile(r'<div class="_a6-p">([^<]+)</div>')


def _entry_time(chunk: str) -> datetime:
    text = _LIKED_AT.search(chunk).group(1)
    local = datetime.strptime(text, "%b %d, %Y %I:%M %p").replace(tzinfo=EXPORT_TZ)
    return local.astimezone(timezone.utc)


def parse_liked_posts(html: str) -> list[tuple[str | None, datetime]]:
    """Return (url, liked_at) for every liked entry, in export order (newest first).

    liked_at is in UTC. The one repeated hour when Pacific time falls back in November is
    ambiguous in the export; it is read as the first (PDT) occurrence.
    """
    entries = []
    for chunk in html.split(_ENTRY)[1:]:
        url = _URL.search(chunk)
        entries.append((url and url.group(1), _entry_time(chunk)))
    return entries


def _first(pattern: re.Pattern, text: str) -> str | None:
    m = pattern.search(text)
    return htmllib.unescape(m.group(1)) if m else None


def parse_posts(html: str, source: str) -> list[dict]:
    """Every entry (Reels and posts) with its searchable metadata, newest first, one per post.

    source is "liked" or "saved"; timestamp is when it was liked/saved, in UTC.
    """
    records, seen = [], set()
    for chunk in html.split(_ENTRY)[1:]:
        url = _URL.search(chunk).group(1)
        parsed = parse_post_url(url)
        shortcode = parsed and parsed[1]
        if (shortcode or url) in seen:  # re-liked later: the newer entry was kept
            continue
        seen.add(shortcode or url)
        # Some entries repeat the caption row; keep each distinct caption once.
        captions = dict.fromkeys(htmllib.unescape(c) for c in _CAPTION.findall(chunk))
        tags = chunk.partition(">Hashtags</h2>")[2].partition(">Owner</h2>")[0]
        # A "Brand partner" block after the Owner has its own Name/Username.
        owner = chunk.partition(">Owner</h2>")[2].partition(">Brand partner</h2>")[0]
        records.append(
            {
                "source": source,
                "url": url,
                "shortcode": shortcode,
                "post_type": {"reel": "reel", "p": "post"}.get(parsed and parsed[0]),
                "caption": "\n".join(captions),
                "hashtags": [htmllib.unescape(t) for t in _HASHTAG.findall(tags)],
                "owner_name": _first(_NAME, owner),
                "username": _first(_USERNAME, owner),
                "timestamp": _entry_time(chunk).isoformat(),
            }
        )
    records.sort(key=lambda r: r["timestamp"], reverse=True)
    return records


def _pattern(query: str) -> re.Pattern | None:
    # Words of a phrase may be split by any whitespace in the caption, including line breaks.
    words = query.split()
    return re.compile(r"\s+".join(map(re.escape, words)), re.IGNORECASE) if words else None


def search_posts(records: list[dict], query: str) -> list[dict]:
    """Records whose caption, hashtags, username or owner name contain query, newest first."""
    pattern = _pattern(query)
    if not pattern:
        return []

    def fields(r):
        yield r["caption"]
        yield from r["hashtags"]
        yield from ("#" + t for t in r["hashtags"])
        if r["username"]:
            yield r["username"]
            yield "@" + r["username"]
        if r["owner_name"]:
            yield r["owner_name"]

    hits = [r for r in records if any(pattern.search(f) for f in fields(r))]
    return sorted(hits, key=lambda r: r["timestamp"], reverse=True)


def snippet(caption: str, query: str, width: int = 50) -> str:
    """One line of caption around the first match, or its start if the match was elsewhere."""
    text = " ".join(caption.split())
    m = _pattern(query).search(text)
    start, end = (max(m.start() - width, 0), m.end() + width) if m else (0, 2 * width)
    return ("..." if start else "") + text[start:end] + ("..." if end < len(text) else "")


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
