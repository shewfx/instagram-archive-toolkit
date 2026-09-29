"""Everything that depends on Instagram's current DOM lives here.

Verified 2026-09-29 on https://www.instagram.com/your_activity/interactions/likes/
(English UI):

- Each liked item is a div[role=button] whose aria-label looks like
  "Video, 3 of 18, by @someone, shared September 27, 2026" or "Photo, 13 of 18, ...".
- Tiles contain no <a href>; the shortcode is only exposed by clicking the tile,
  which navigates the tab to https://www.instagram.com/p/<shortcode>.
- The grid scrolls inside its own container, not the page, and lazy-loads more tiles.
- Navigating back re-renders the grid from the top, so the scanner must scroll again.
"""

LIKED_TILE = '[role=button][aria-label^="Video,"], [role=button][aria-label^="Photo,"]'


def is_video(aria_label: str | None) -> bool:
    # ponytail: "Video" is treated as "Reel"; the grid does not distinguish them.
    return bool(aria_label) and aria_label.startswith("Video,")


# URL glob Instagram navigates to after clicking a tile.
POST_URL_GLOB = "**/p/**"

# Scroll the nearest scrollable ancestor of the first tile by one viewport.
# Uses computed style rather than class names, which are obfuscated and change often.
SCROLL_GRID_JS = """
(tile) => {
  let el = tile.parentElement;
  while (el && !(/(auto|scroll)/.test(getComputedStyle(el).overflowY)
                 && el.scrollHeight > el.clientHeight)) {
    el = el.parentElement;
  }
  (el || document.scrollingElement).scrollBy(0, (el || window).clientHeight || 800);
}
"""


# --- Phase 2: saving. Verified 2026-09-29 on https://www.instagram.com/p/<shortcode>/ ---
#
# - The post's bookmark is a [role=button] holding svg[aria-label="Save"] when unsaved and
#   svg[aria-label="Remove"] once saved (to All posts, whatever the collections).
# - Clicking Save also opens a "Collections" popover. The tool never touches it; it closes when
#   the next Reel opens. Clicking Remove would unsave, so the tool never clicks it.
UNSAVED = '[role=button]:has(svg[aria-label="Save"])'
SAVED = '[role=button]:has(svg[aria-label="Remove"])'
# Text Instagram shows for a deleted or private post.
UNAVAILABLE_TEXT = r"this page isn.t available"
# Only consulted after an expected step failed. Unverified: none of these could be observed.
BLOCK_TEXT = r"try again later|we restrict certain activity|action blocked"
