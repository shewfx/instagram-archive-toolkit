# Insta Likes to Reels

A personal automation tool that takes Instagram Reels I have liked and saves them to my Instagram
Saved posts.

It drives a normal Chrome window through the Instagram website, logged in as you. It does not use any
private or unofficial Instagram API, and it never sees your password.

## Status

**Phase 1 — implemented:** find liked Reels and store them locally in SQLite, either from an
Instagram data export (recommended) or by scanning the likes page.

**Phase 2 — implemented:** save pending Reels to Instagram's Saved posts (All posts), oldest like
first. Adding them to a specific collection was tried and dropped; see [Limitations](#limitations).

## Requirements

- Windows, macOS or Linux with **Google Chrome** installed (Playwright drives your installed Chrome)
- Python 3.10+

## Setup

```sh
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

No `playwright install` step is needed, because the tool uses your installed Chrome.

## Authentication

The tool keeps its own Chrome profile in `browser-profile/`, separate from your normal Chrome profile.
To log in:

```sh
python -m src.cli login
```

A Chrome window opens at the Instagram login page. Log in yourself (including any 2FA), then close
the window. The session is stored in `browser-profile/` and reused by every later command. If it
expires, `save` and `scan` stop and tell you to run `login` again.

> **Warning:** `browser-profile/` contains your Instagram session cookies, and `data/` contains your
> liked-Reels history. Both are listed in `.gitignore`. **Never commit them, never force-add them, and
> never share them.** Anyone with the profile folder can act as your Instagram account. Keep the
> Instagram export itself outside this repository too.

## Usage

The main workflow has three steps: turn an Instagram data export into a local list of liked Reels,
import it into SQLite, then save the Reels on Instagram.

### 1. Instagram export → JSON

Request your data from Instagram (Accounts Center → Your information and permissions → Download
your information) in **HTML** format, including "Likes". Unzip it anywhere outside this repository,
then run:

```sh
python -m src.cli parse-export <export>/your_instagram_activity/likes/liked_posts.html
```

This is fully offline: it reads the HTML file and never contacts Instagram. It writes
`data/liked_reels_export.json` (gitignored):

```json
[
  {
    "shortcode": "ABC123",
    "url": "https://www.instagram.com/reel/ABC123/",
    "type": "reel",
    "liked_at": "2026-09-28T09:46:00+00:00"
  }
]
```

- Only explicit `/reel/` links are kept. Photos and other posts (`/p/`) are skipped.
- Only Reels liked at or after `EXPORT_SINCE` in `src/config.py` are kept (default
  2025-01-01 00:00 UTC).
- Each shortcode appears once, newest first, as in the export.
- The export writes its times in US Pacific time, wherever you are. `liked_at` is converted to UTC.

### 2. Import into SQLite

```sh
python -m src.cli import-export
```

This adds every Reel from `data/liked_reels_export.json` to `data/reels.db` as `pending`. Running
it again is safe. Reels already in the database keep their status and history; they only gain a
`liked_at` if they had none.

### 3. Save the Reels on Instagram

Start with a dry run, then a small batch:

```sh
python -m src.cli save --dry-run --limit 5   # open 5 Reels, report their state, click nothing
python -m src.cli save --limit 5
python -m src.cli status
```

For each pending Reel, `save` opens `instagram.com/p/<shortcode>/` directly and reads the bookmark
control:

- **Save** → clicks it **once**, waits until it changes to **Remove**, then records `saved`.
- **Remove** → the Reel is already saved. It is **never clicked** (that would unsave it) and is
  recorded as `saved`.
- **"Sorry, this page isn't available"** → recorded as `unavailable` (deleted or private).

Clicking Save also opens Instagram's Collections popover. The tool ignores it; it closes when the
next Reel opens.

**Order: oldest like first.** Pending Reels are processed by `liked_at`, oldest first. Instagram
shows the most recently saved posts at the top, so when the migration finishes your newest likes
are at the top of Saved. Reels with no `liked_at` (found only by the likes-page scanner) go last.

**Options:**

- `--limit N` stops after N Reels.
- `--dry-run` opens each Reel and reports whether it would be saved, is already saved or is
  unavailable. It clicks nothing and writes nothing to the database.

At the end, `save` prints the counts, the average seconds per Reel, and an estimate for the Reels
still pending.

**Resuming.** Each Reel's result is written to `data/reels.db` as soon as that Reel is done, with
`processed_at` in UTC. If Chrome crashes, you press **Ctrl+C**, or the run stops on a warning, just
run `save` again: it continues with the oldest Reel that is still `pending`. Nothing is redone.

**Statuses** (`python -m src.cli status` shows the counts):

| Status | Meaning |
|---|---|
| `pending` | not processed yet; the next `save` picks these up |
| `saved` | saved on Instagram: either clicked by the tool, or it already showed Remove |
| `failed` | this Reel's page did not behave as expected (see `last_error`). Not retried automatically. |
| `unavailable` | Instagram says the post no longer exists or is private |

To retry failed Reels, set them back to `pending` in `data/reels.db`
(`UPDATE reels SET status = 'pending' WHERE status = 'failed'`).

## Optional: scanning the likes page

**Not needed for the main Jan 2025+ migration.** The export covers that history completely and
much faster. The scanner is useful for likes newer than your latest export.

```sh
python -m src.cli scan --limit 5
python -m src.cli list-pending
```

Run `scan` without `--limit` to go through your likes history. Press **Ctrl+C** to stop at any
time; everything found so far is already saved. Running `scan` again is safe: Reels are stored by
shortcode and never inserted twice.

### Repeat scans stop early

The likes page lists newest first. Once your history has been scanned, a later scan only needs the
new likes at the top. So by default a scan stops after **10 already-known Reels in a row**:

```sh
python -m src.cli scan                          # stops after 10 known in a row (default)
python -m src.cli scan --stop-after-known 25    # a larger safety margin
python -m src.cli scan --stop-after-known 0     # never stop early; scan the full history
```

Only Reels that were opened successfully and are already in the database count toward the streak.
A new Reel resets it to 0. Photos, other tile types and failed items never count.

`--limit` works independently: `scan --limit 5` opens at most 5 Reels, whatever the streak setting.

> **If your first full scan was interrupted,** resume it with `--stop-after-known 0`. Otherwise the
> rerun reaches the Reels it already found and stops before the older, unscanned part.

### Historical cutoff

To scan history only back to a certain Reel, store that Reel's shortcode once:

```sh
python -m src.cli set-cutoff <shortcode>
```

`scan` reads the cutoff from `data/reels.db` once at startup. When it reaches that Reel, it stores
it normally, prints that the cutoff was reached, and stops; nothing older is opened. Checking for
the cutoff costs nothing extra: it is a plain comparison with the shortcode the scan already has,
with no additional Instagram request, navigation or database query. `status` shows the current
cutoff. Running `set-cutoff` again replaces it.

The cutoff works alongside `--limit` and `--stop-after-known`; whichever is reached first ends the
scan.

### How the scanner works

Instagram's likes page (`Your activity → Interactions → Likes`) shows liked items as a grid of
tiles. As of 2026-09-29, those tiles contain **no links**. Each one is a button labeled like
`Video, 3 of 18, by @someone, shared September 27, 2026`. The only way to find out which post a
tile is, is to click it, which opens `instagram.com/p/<shortcode>`. The scanner therefore:

1. opens the likes page and skips tiles labeled `Photo`
2. clicks each `Video` tile and reads the shortcode from the URL
3. stores `https://www.instagram.com/p/<shortcode>/` in SQLite
4. reopens the likes page and scrolls back down to the next tile

Opening a liked item leaves the likes page, and coming back reloads the grid from the top. So for
the 200th Reel, the scanner has to scroll past the first 199 again. An estimate for ~250 Reels is
**2–3 hours**. This is why the export is the recommended source.

## Instagram's website

The tool drives the normal Instagram website in a real Chrome window, the same pages you would
click through. It does **not** call Instagram's private or unofficial APIs or read their responses.

All Instagram DOM details live in `src/instagram/selectors.py`. **When Instagram changes its
website, those selectors can break.** A `save` run where every Reel fails with "no Save button
appeared", or a scan that suddenly finds 0 items, is the usual sign.

## Pacing and safety

This is meant for a real, personal account. It favors reliability over speed and makes no attempt
to hide that it is automation. Settings are in `src/config.py`:

| Setting | Default | Meaning |
|---|---|---|
| `ACTION_DELAY` | 2.0 s | pause between a Reel's page loading and clicking Save |
| `ITEM_DELAY` | 5.0 s | pause after each Reel (and after opening each liked item in `scan`) |
| `SCROLL_DELAY` | 3.0 s | pause between scrolls of the likes grid |
| `NAV_TIMEOUT` | 20 s | how long to wait for a page or control before treating it as failed |
| `MAX_IDLE_SCROLLS` | 4 | scrolls in a row with nothing new before the list counts as finished |
| `STOP_AFTER_KNOWN` | 10 | default for `--stop-after-known` |
| `MAX_CONSECUTIVE_ERRORS` | 3 | failed Reels or items in a row that end a run |

`save` takes about 8–9 s per Reel, roughly 400–450 Reels an hour. Prefer batches of a few hundred
with breaks over one very long run.

- **One session only.** Chrome locks `browser-profile/`, so a second `save`, `scan` or `login`
  cannot start while one is running.
- **No automatic retries.** A failed Reel is recorded and skipped, never retried in the same run.
- **Stops on anything unexpected.** If opening a Reel lands anywhere other than that Reel's page
  (a login page, a challenge, a checkpoint), the run stops immediately. It also stops after 3
  failed Reels in a row. Progress is always kept.
- **Warning text.** When an expected step fails, the page is checked for "Try again later", "We
  restrict certain activity" or "Action blocked", and the run stops if one is shown. These texts
  could not be observed on a healthy account, so this check is unverified. If you ever see such a
  warning, stop using the tool for a while.

## Limitations

- **No collection.** Reels go to Saved (All posts), not to a named collection. The post page never
  shows which collection a saved post is in, and Instagram's collection picker could not be driven
  reliably, so collection support was dropped. Reels that already show Remove stay exactly where
  they are.
- **English UI only.** Tile labels (`Video,` / `Photo,`) and the "page isn't available" text are
  matched in English.
- **Export times in the repeated November hour.** When Pacific time falls back, one hour happens
  twice and the export does not say which. Those likes are read as the first occurrence, so their
  `liked_at` may be an hour early.
- **Scanner: "Video" is treated as "Reel".** The likes grid does not distinguish Reels from other
  video posts. Newly liked items can also shift the grid during a scan; the next scan picks up
  anything skipped.

## Development

```sh
python -m pytest
ruff format src tests && ruff check src tests
```
