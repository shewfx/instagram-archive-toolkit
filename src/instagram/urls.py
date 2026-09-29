import re
from urllib.parse import urljoin

# Matches /reel/<code>, /reels/<code>, /p/<code>, optionally prefixed by /<username>/.
_SHORTCODE = re.compile(r"^/(?:[\w.]+/)?(reels?|p)/([A-Za-z0-9_-]+)/?$")


def parse_post_url(href: str) -> tuple[str, str] | None:
    """Return (kind, shortcode) for an Instagram post/reel link, else None.

    kind is "reel" or "p". Query strings and fragments are ignored.
    """
    if not href:
        return None
    url = urljoin("https://www.instagram.com/", href)
    m = re.match(r"^https?://(?:www\.)?instagram\.com(/[^?#]*)", url)
    if not m:
        return None
    path = m.group(1)
    if not path.endswith("/"):
        path += "/"
    m = _SHORTCODE.match(path)
    if not m:
        return None
    kind = "reel" if m.group(1).startswith("reel") else "p"
    return kind, m.group(2)


def post_url(shortcode: str) -> str:
    # /p/<code>/ is what Instagram itself navigates to from the likes grid.
    # /reel/<code>/ was observed redirecting to a different reel, so it is not used.
    return f"https://www.instagram.com/p/{shortcode}/"
