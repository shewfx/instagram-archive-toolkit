# Insta Likes to Reels

A personal tool for an Instagram account's history of likes and saves. It does three things:

1. **Moves liked Reels into Saved.** It reads your liked Reels from Instagram's data export, then
   saves each one to your Saved posts, oldest like first, so your newest likes end up at the top.
2. **Searches everything you liked or saved.** It searches captions, hashtags, usernames and owner
   names across every liked and saved Reel and post. This works fully offline, from the export.
3. **Gives you a local control panel.** A dashboard runs the saver in the background, shows
   progress live, and holds search, failed items, settings and logs.

The saver drives a normal Chrome window on the Instagram website, logged in as you. It uses no
private or unofficial Instagram API, and it never sees your password. Search never contacts
Instagram at all.

## Contents

- [Requirements](#requirements)
- [Setup](#setup)
- [Quick start](#quick-start)
- [Control panel](#control-panel)
- [Saving liked Reels](#saving-liked-reels)
- [Searching liked and saved posts](#searching-liked-and-saved-posts)
- [Command reference](#command-reference)
- [Pacing and safety](#pacing-and-safety)
- [Settings](#settings)
- [Your data](#your-data)
- [Optional: scanning the likes page](#optional-scanning-the-likes-page)
- [Limitations](#limitations)
- [Project layout](#project-layout)
- [Development](#development)

## Requirements

- Windows, macOS or Linux with **Google Chrome** installed (Playwright drives your installed Chrome)
- Python 3.10 or newer
- An Instagram data export in **HTML** format (see [step 1](#1-get-your-instagram-export))

## Setup

```sh
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

No `playwright install` step is needed, because the tool uses your installed Chrome.

Then log in once:

```sh
python -m src.cli login
```

A Chrome window opens at the Instagram login page. Log in yourself (including any 2FA), then close
the window. The session is kept in `browser-profile/`, a Chrome profile separate from your normal
one, and reused by every later run. If it expires, the saver stops and asks you to log in again.

> **Your login stays on your computer.** The repository ships with no browser profile, cookies or
> account data. Everyone creates their own `browser-profile/` locally with `login`. It holds live
> session cookies, so anyone who gets a copy can act as your Instagram account. It is gitignored:
> **never commit it, force-add it, upload it or share it.** See [Your data](#your-data).

## Quick start

With an export unzipped outside this folder (`<export>` below):

```sh
# Liked Reels -> local database
python -m src.cli parse-export "<export>/your_instagram_activity/likes/liked_posts.html"
python -m src.cli import-export

# Search index for liked and saved posts
python -m src.cli build-search --liked "<export>/your_instagram_activity/likes/liked_posts.html" --saved "<export>/your_instagram_activity/saved/saved_posts.html"

# Control panel
python -m src.ui
```

Open http://localhost:8080. On Windows, without activating the venv, use
`.\.venv\Scripts\python.exe` in place of `python`.

## Control panel

```sh
python -m src.ui
```

A local dashboard at http://localhost:8080 that runs the same code as the CLI. It listens on this
computer only (127.0.0.1).

| Page | What it does |
|---|---|
| **Dashboard** | Counts for every status, overall progress, and the saver. Choose a batch (10, 25, 50 or all pending Reels) and press **Start / Resume**. The live run shows the current Reel, processed, newly saved, already saved, failures, elapsed time, seconds per Reel, Reels per hour and ETA. **Stop safely** finishes the current Reel, then stops. |
| **Search** | Search liked, saved or all posts, 100 results per page by default (25, 50 or 200 also available). Every result keeps a global number across pages, so you can track what you've checked. |
| **Failed items** | Each failed Reel with its error. Open it, reset it to pending, or mark it skipped so it's never retried. **Reset all failed to pending** asks for confirmation first. |
| **Exports** | Whether each export file exists, how many entries and Reels it has, when the search index was built, and **Rebuild Search Index**. |
| **Settings** | Export paths, database path, browser profile folder, pause per Reel and default batch size. See [Settings](#settings). |
| **Logs** | Live saver output, and earlier runs from `data/logs/` (read-only). |

How the saver behaves in the panel:

- It runs in a background thread, so the page stays responsive. Only one saver runs at a time.
- Closing or reloading the browser tab does not stop it. **Ctrl+C** on the server stops it after
  the current Reel.
- It stops by itself on the same conditions as the CLI (see [Pacing and safety](#pacing-and-safety)),
  and the status turns to **Stopped: warning/error** with the reason.
- Don't run `save` from the CLI at the same time. Chrome refuses to open the same profile twice, so
  the second run would stop with an error.

## Saving liked Reels

The workflow has three steps: turn the export into a list of liked Reels, import it into SQLite,
then save the Reels on Instagram.

### 1. Get your Instagram export

Request your data from Instagram (Accounts Center → Your information and permissions → Download
your information) in **HTML** format, including "Likes" and "Saved". Unzip it anywhere outside this
repository.

### 2. Parse and import

```sh
python -m src.cli parse-export "<export>/your_instagram_activity/likes/liked_posts.html"
python -m src.cli import-export
```

`parse-export` is fully offline. It writes `data/liked_reels_export.json`:

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
- Only Reels liked at or after `EXPORT_SINCE` are kept. The default is 2025-01-01 00:00 UTC. To
  use your own cutoff and time zone, add it to `data/settings.json`, e.g.
  `"EXPORT_SINCE": "2024-06-01T00:00:00+02:00"`.
- Each shortcode appears once. The export writes times in US Pacific time wherever you are, and
  `liked_at` is converted to UTC.

`import-export` adds every Reel to `data/reels.db` as `pending`. Running it again is safe: Reels
already in the database keep their status and history.

### 3. Save them

From the [control panel](#control-panel), or from the CLI. Start with a dry run and a small batch:

```sh
python -m src.cli save --dry-run --limit 5   # open 5 Reels, report their state, click nothing
python -m src.cli save --limit 5
python -m src.cli status
```

For each pending Reel, the saver opens `instagram.com/p/<shortcode>/` and reads the bookmark
control:

- **Save**: clicks it **once**, waits until it changes to **Remove**, then records `saved`. A Reel
  is never recorded as saved until Remove is showing.
- **Remove**: the Reel is already saved. It is **never clicked** (that would unsave it) and is
  recorded as `saved`.
- **"Sorry, this page isn't available"**: recorded as `unavailable` (deleted or private).

Clicking Save also opens Instagram's Collections popover. The tool ignores it; it closes when the
next Reel opens.

**Order.** Pending Reels go oldest like first. Instagram shows the most recently saved posts at the
top, so when the migration finishes your newest likes are at the top of Saved. Reels with no
`liked_at` (found only by the likes-page scanner) go last.

**Options** (one of `--limit` or `--all` is required):

- `--limit N` stops after N Reels.
- `--all` keeps going until no pending Reels are left.
- `--dry-run` opens each Reel and reports whether it would be saved, is already saved or is
  unavailable. It clicks nothing and writes nothing to the database.

Every 25 Reels, and at the end, `save` prints a progress line: processed, newly saved, already
saved, unavailable, failed, pending, elapsed time, seconds per Reel and estimated time left.
Everything is also written, with timestamps, to `data/logs/save-<date>-<time>.log`.

**Resuming.** Each Reel's result is written to the database as soon as that Reel is done. If Chrome
crashes, you press **Ctrl+C**, or the run stops on a warning, run `save` again: it continues with
the oldest Reel that is still pending. Nothing is redone.

**Unattended runs.** For the whole backlog, from the project folder in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m src.cli save --all
```

Leave the terminal and its Chrome window running, and don't use that Chrome window yourself. Keep
the computer awake and online: sleep pauses the run, and Reels that time out after waking count as
failures. Check progress from another window with `status`, or in the control panel.

### Statuses

| Status | Meaning |
|---|---|
| `pending` | Not processed yet. The next run picks these up. |
| `saved` | Saved on Instagram: clicked by the tool, or it already showed Remove. |
| `failed` | The Reel's page didn't behave as expected (see its error). Not retried automatically. |
| `unavailable` | Instagram says the post no longer exists or is private. |
| `skipped` | Set by hand from **Failed items**. Never retried. |

To retry failed Reels, use **Failed items** in the control panel.

## Searching liked and saved posts

Search covers every liked and saved Reel and post in the export (`/reel/` and `/p/` links), and
never contacts Instagram. Build the index once from the export:

```sh
python -m src.cli build-search --liked "<export>/your_instagram_activity/likes/liked_posts.html" --saved "<export>/your_instagram_activity/saved/saved_posts.html"
```

This writes `data/liked_posts_export.json` and `data/saved_posts_export.json`. Each record keeps
the source, URL, shortcode, post type, caption, hashtags, owner name, username and the time it was
liked or saved. Rebuild after downloading a newer export, or use **Rebuild Search Index** on the
Exports page.

Then search, in the control panel or the CLI:

```sh
python -m src.cli search-liked "harry potter"
python -m src.cli search-saved "resident evil"
python -m src.cli search-all "gym motivation"
```

- Matching ignores case and covers captions, hashtags, usernames and owner names.
- Phrases match across line breaks in a caption. `#tag` and `@username` also work.
- Emoji and non-English captions are decoded correctly.
- Results are newest first. Each shows LIKED or SAVED, the link, `@username`, owner name, date and
  the part of the caption that matched.

The export contains no thumbnails for liked or saved posts, so results are text only.

## Command reference

All commands run as `python -m src.cli <command>`.

| Command | What it does | Contacts Instagram |
|---|---|---|
| `login` | Opens Chrome so you can log in; the session is kept in `browser-profile/` | Yes |
| `parse-export HTML` | Liked Reels from `liked_posts.html` → `data/liked_reels_export.json` | No |
| `import-export` | Adds those Reels to `data/reels.db` as pending | No |
| `save --limit N` / `--all` | Saves pending Reels, oldest like first. `--dry-run` clicks nothing. | Yes |
| `status` | Counts by status, and the scanner's cutoff | No |
| `list-pending` | Lists Reels not yet processed | No |
| `build-search --liked HTML --saved HTML` | Builds the search index | No |
| `search-liked` / `search-saved` / `search-all "text"` | Searches the index | No |
| `scan` | Finds liked Reels on the likes page (see [scanning](#optional-scanning-the-likes-page)) | Yes |
| `set-cutoff SHORTCODE` | Oldest Reel `scan` should reach | No |

The control panel is `python -m src.ui`.

## Pacing and safety

This is meant for a real, personal account. It favors reliability over speed and makes no attempt
to hide that it is automation.

- **Slow by design.** The saver pauses 2 s before clicking Save and 5 s after each Reel: about
  8–9 s per Reel, roughly 400–450 Reels an hour.
- **One session only.** Chrome locks `browser-profile/`, so a second saver, scan or login can't
  start while one is running. The control panel also allows only one saver at a time.
- **No automatic retries.** A failed Reel is recorded and skipped, never retried in the same run.
- **Stops by itself**, keeping all progress and giving the reason, when:
  - Instagram answers any request with **HTTP 429** (Too Many Requests). The run stops before the
    next Reel. If the current Reel's Save wasn't confirmed, it stays pending.
  - opening a Reel lands on a login page, a challenge/checkpoint, or anywhere other than that Reel
  - Instagram shows an action warning ("Try again later", "We restrict certain activity", "Action
    blocked")
  - Chrome is closed or crashes (the Reel in progress stays pending)
  - 3 Reels in a row fail
- **After a warning or 429, wait.** Stop using the tool for a while before resuming. There is
  nothing in the tool to get around Instagram's limits, and there shouldn't be.

The action-warning texts could not be observed on a healthy account, so that check is unverified.

## Settings

Defaults live in `src/config.py`. The control panel's **Settings** page can override a few of them.
It saves them to `data/settings.json`, which the CLI reads too, so both always agree.

| Setting | Default | Editable in the panel | Meaning |
|---|---|---|---|
| Liked / saved HTML paths | not set | Yes | Export files used by **Rebuild Search Index** |
| `DB_PATH` | `data/reels.db` | Yes | The saver's progress database |
| `PROFILE_DIR` | `browser-profile/` | Yes | Chrome profile holding the login |
| `ITEM_DELAY` | 5.0 s | Yes, but only upward | Pause after each Reel. It can't be set below 5 s. |
| `BATCH_SIZE` | 25 | Yes | Batch preselected on the dashboard |
| `ACTION_DELAY` | 2.0 s | No | Pause between a Reel's page loading and clicking Save |
| `NAV_TIMEOUT` | 20 s | No | Wait for a page or control before treating it as failed |
| `MAX_CONSECUTIVE_ERRORS` | 3 | No | Failed Reels in a row that end a run |
| `EXPORT_SINCE` | 2025-01-01T00:00:00Z | In `data/settings.json` | Oldest like `parse-export` keeps. An ISO time with an offset. |
| `SCROLL_DELAY`, `MAX_IDLE_SCROLLS`, `STOP_AFTER_KNOWN` | 3.0 s, 4, 10 | No | Likes-page scanner pacing |

Database and profile changes apply to the next saver run.

## Your data

Everything personal stays on your computer and out of git:

| Path | Contains |
|---|---|
| `browser-profile/` | Your Instagram session cookies. **Anyone with this folder can act as your account.** |
| `data/reels.db` (and any backups) | Every liked Reel and its save status |
| `data/*_export.json` | Parsed likes and the search index |
| `data/settings.json` | Your local settings (paths and pacing only; no cookies or sessions) |
| `data/logs/` | One log per saver run |

All of these are in `.gitignore`. **Never commit them, never force-add them, and never share
them.** Keep the Instagram export itself outside this repository too. `.gitignore` also covers
export folders, `.zip` files, `.env` files, logs and database files copied in by mistake, but it is
a safety net, not a place to keep them.

## Optional: scanning the likes page

**Not needed if you have an export.** The export covers your history completely and much faster.
The scanner is useful for likes newer than your latest export.

```sh
python -m src.cli scan --limit 5
python -m src.cli list-pending
```

Running `scan` again is safe: Reels are stored by shortcode and never inserted twice. Press
**Ctrl+C** to stop at any time; everything found so far is kept.

**Repeat scans stop early.** The likes page lists newest first, so by default a scan stops after
**10 already-known Reels in a row**. Use `--stop-after-known 25` for a larger margin, or
`--stop-after-known 0` to scan the full history. If your first full scan was interrupted, resume it
with `--stop-after-known 0`; otherwise the rerun stops at the Reels it already found.

**Historical cutoff.** `set-cutoff <shortcode>` makes `scan` stop once it reaches and stores that
Reel. `status` shows the current cutoff. The cutoff, `--limit` and `--stop-after-known` all apply;
whichever is reached first ends the scan.

**Why it's slow.** As of 2026-09-29, the likes grid's tiles contain no links. Each is a button
labeled like `Video, 3 of 18, by @someone, shared September 27, 2026`, and the only way to learn
its shortcode is to click it. Coming back reloads the grid from the top, so the scanner has to
scroll past every earlier tile again. About 250 Reels take 2–3 hours.

## Limitations

- **Instagram's website changes.** All page details live in `src/instagram/selectors.py`. A save
  run where every Reel fails with "no Save button appeared", or a scan that finds 0 items, usually
  means Instagram changed its page and a selector needs updating.
- **No collections.** Reels go to Saved (All posts), not a named collection. The post page never
  shows which collection a saved post is in, and Instagram's collection picker couldn't be driven
  reliably. Reels that already show Remove stay exactly where they are.
- **English UI only.** Tile labels and the "page isn't available" text are matched in English.
- **The repeated November hour.** When Pacific time falls back, one hour happens twice and the
  export doesn't say which. Those likes are read as the first occurrence, so their time may be an
  hour early.
- **Scanner: "Video" means "Reel".** The likes grid doesn't distinguish Reels from other videos.
- **No thumbnails.** The export has no images for liked or saved posts, so search results are text
  only.

## Project layout

```text
src/
  cli.py                 command-line interface
  config.py              defaults, plus local overrides from data/settings.json
  database.py            SQLite: reels, statuses, migrations
  services.py            operations shared by the CLI and the control panel
  instagram/
    export.py            parses liked_posts.html / saved_posts.html; search
    saver.py             the save loop, and the Save / Remove handling
    likes_scanner.py     optional likes-page scanner
    selectors.py         everything that depends on Instagram's page structure
    urls.py              shortcode and URL parsing
  ui/
    app.py               control panel entry point (python -m src.ui)
    state.py             the single background saver worker
    components/          shared layout, theme and widgets
    pages/               dashboard, search, failed, exports, settings, logs
tests/                   pytest suite; no test opens a browser or contacts Instagram
```

## Development

```sh
python -m pytest
ruff format src tests
ruff check src tests
```

## License

[MIT](LICENSE)
