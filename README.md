# Insta Likes to Reels

A personal automation tool that takes Instagram Reels I have liked and saves them into a specific Saved collection.

It drives a normal Chrome window through the Instagram website, logged in as you. It does not use any
private or unofficial Instagram API, and it never sees your password.

## Status

**Phase 1 — implemented:** discover liked Reels and store them locally in SQLite.

**Phase 2 — not started:** save pending Reels into a Saved collection.

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
expires, `scan` tells you to run `login` again.

> **Warning:** `browser-profile/` contains your Instagram session cookies, and `data/` contains your
> liked-Reels history. Both are listed in `.gitignore`. **Never commit them, never force-add them, and
> never share them.** Anyone with the profile folder can act as your Instagram account.

## Usage

Start with a small test scan:

```sh
python -m src.cli scan --limit 5
```

Then check the results:

```sh
python -m src.cli status
python -m src.cli list-pending
```

Run `scan` without `--limit` to go through your likes history. Press **Ctrl+C** to stop at any
time; everything found so far is already saved. Running `scan` again is safe: Reels are stored by
shortcode and never inserted twice.

The database is `data/reels.db`. New Reels start with status `pending`.

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

To import history only back to a certain Reel, store that Reel's shortcode once:

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

## How it works

The scanner drives the normal Instagram website in a real Chrome window, the same pages you would
click through. It does **not** call Instagram's private or unofficial APIs or read their responses.

Instagram's likes page (`Your activity → Interactions → Likes`) shows liked items as a grid of
tiles. As of 2026-09-29, those tiles contain **no links**. Each one is a button labeled like
`Video, 3 of 18, by @someone, shared September 27, 2026`. The only way to find out which post a
tile is, is to click it, which opens `instagram.com/p/<shortcode>`. The scanner therefore:

1. opens the likes page and skips tiles labeled `Photo`
2. clicks each `Video` tile and reads the shortcode from the URL
3. stores `https://www.instagram.com/p/<shortcode>/` in SQLite
4. reopens the likes page and scrolls back down to the next tile

All Instagram DOM details live in `src/instagram/selectors.py`. **When Instagram changes its
website, those selectors can break.** A scan that suddenly finds 0 items or stops with "no liked
items appeared" is the usual sign.

### Why first scans are slow

Opening a liked item leaves the likes page, and coming back reloads the grid from the top. So for
the 200th Reel, the scanner has to scroll past the first 199 again. The pacing delays below come on
top of that. An estimate for ~250 Reels is **2–3 hours**; use `--limit` to spread it over several
sessions (resume with `--stop-after-known 0`, see above). Repeat scans are fast because they stop
after a short streak of known Reels.

## Pacing and safety

This is meant for a real, personal account. It favors reliability over speed and makes no attempt
to hide that it is automation. Settings are in `src/config.py`:

| Setting | Default | Meaning |
|---|---|---|
| `SCROLL_DELAY` | 3.0 s | pause between scrolls of the likes grid |
| `ITEM_DELAY` | 5.0 s | pause after opening each liked item |
| `NAV_TIMEOUT` | 20 s | how long to wait for a page or item before treating it as failed |
| `MAX_IDLE_SCROLLS` | 4 | scrolls in a row with nothing new before the list counts as finished |
| `STOP_AFTER_KNOWN` | 10 | default for `--stop-after-known` |
| `MAX_CONSECUTIVE_ERRORS` | 3 | failed items in a row that end the scan |

- **One session only.** Chrome locks `browser-profile/`, so a second scan or `login` cannot start
  while one is running.
- **No automatic retries.** A failed item is counted and skipped, never retried.
- **Stops on anything unexpected.** The scanner only ever expects two kinds of page: the likes page
  and `instagram.com/p/<shortcode>`. If Instagram sends it anywhere else (a login page, a
  challenge, a checkpoint), or the likes page loads with no items, it stops immediately. It also
  stops after 3 failed items in a row, which is how a popup blocking clicks would most likely show up. Progress is
  always kept.
- **Limitation: no specific CAPTCHA or action-block detection.** None of these screens could be
  observed on a healthy account, so there are no selectors or text matches for "Try again later",
  CAPTCHAs or suspicious-login warnings. The rules above catch them only indirectly. If a warning
  appears as a popup on the likes page, the scanner may spend up to 3 × `NAV_TIMEOUT` before
  stopping. If you ever see such a warning, stop using the tool for a while.

## Limitations

- **"Video" is treated as "Reel".** The likes grid does not distinguish Reels from other video
  posts. Since Instagram converted feed videos to Reels, these are usually the same thing.
- **English UI only.** The tile labels (`Video,` / `Photo,`) are matched in English.
- **Newly liked items shift the order.** If you like something while a scan is running, one item
  may be skipped. The next scan will pick it up.

## Development

```sh
python -m pytest
ruff format src tests && ruff check src tests
```
