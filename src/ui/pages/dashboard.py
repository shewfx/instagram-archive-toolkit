"""Dashboard: archive progress, saver controls and the live run, as one panel."""

import sqlite3

from nicegui import run, ui

from src import config, database, services
from src.instagram.urls import post_url
from src.ui.components.layout import frame
from src.ui.components.widgets import field, ruler_html, stat, status_badge
from src.ui.state import batch_options, hms, metrics, percent_done, worker


@ui.page("/")
def dashboard():
    with frame("Dashboard", "/"), ui.element("div").classes("panel w-full divide"):
        # Header: what this panel is, and the saver's state.
        with ui.row().classes("panel-head w-full items-center"):
            ui.label("Archive").classes("text-base font-semibold")
            ui.space()
            ui.label("Liked Reels, saved oldest first").classes("eyebrow")

        # Progress: saved Reels as the headline number, over the tick ruler.
        with ui.column().classes("panel-body w-full gap-4"):
            with ui.row().classes("w-full items-end justify-between gap-4"):
                with ui.column().classes("gap-2"):
                    ui.label("Saved").classes("eyebrow")
                    with ui.row().classes("items-baseline gap-2 no-wrap"):
                        saved = ui.label("–").classes("big-number")
                        of_total = ui.label().classes("mono text-lg faint")
                with ui.column().classes("items-end gap-2"):
                    ui.label("Complete").classes("eyebrow")
                    percent = ui.label("–").classes("big-number accent")
            ruler = ui.html(ruler_html(0, 0), sanitize=False).classes("w-full")
            with ui.row().classes("w-full justify-between mono text-xs faint"):
                ui.label("0")
                midpoint = ui.label()
                end = ui.label()

        # Every status count in one strip.
        with ui.grid().classes("panel-body w-full gap-4 grid-cols-2 sm:grid-cols-5"):
            pending = stat("pending", "amber")
            failed = stat("failed", "red")
            unavailable = stat("unavailable")
            skipped = stat("skipped")
            total = stat("total discovered")

        # Saver controls and the live run, side by side.
        with ui.grid().classes("panel-body w-full gap-8 grid-cols-1 md:grid-cols-5"):
            with ui.column().classes("gap-4 md:col-span-2"):
                with ui.row().classes("w-full items-center"):
                    ui.label("Saver").classes("eyebrow")
                    ui.space()
                    badge = status_badge()
                sizes = {n: "All" if n == 0 else str(n) for n in batch_options()}
                with ui.row().classes("items-center gap-3"):
                    ui.label("Process").classes("muted")
                    batch = ui.toggle(sizes, value=config.BATCH_SIZE).classes("segmented")
                    batch.props(
                        "unelevated no-caps dense toggle-color=grey-3 toggle-text-color=black"
                    )
                with ui.row().classes("items-center gap-2"):
                    start = ui.button("Start / Resume", color=None, on_click=lambda: _start())
                    start.classes("pill btn-primary").props("unelevated")
                    stop = ui.button("Stop safely", color=None, on_click=lambda: worker.stop())
                    stop.classes("pill btn-quiet").props("flat")
                message = ui.label().classes("muted text-sm")
            with ui.column().classes("gap-4 md:col-span-3"):
                ui.label("This run").classes("eyebrow")
                idle_note = ui.label("No run since the UI started.").classes("muted text-sm")
                with ui.column().classes("w-full gap-4") as details:
                    current = ui.link("–", "#", new_tab=True).classes("mono text-sm accent")
                    with ui.grid().classes("w-full gap-x-6 gap-y-4 grid-cols-2 sm:grid-cols-3"):
                        processed = field("Processed")
                        newly = field("Newly saved")
                        already = field("Already saved")
                        failures = field("Failures")
                        elapsed = field("Elapsed")
                        avg = field("Seconds/Reel")
                        per_hour = field("Reels/hour")
                        remaining = field("Remaining in batch")
                        eta = field("ETA")

        with ui.row().classes("panel-body w-full items-center justify-between gap-2"):
            ui.label(f"{config.ITEM_DELAY:g} s pause per Reel").classes("eyebrow")
            ui.label("Stops by itself on login, challenge, warnings or HTTP 429").classes(
                "faint text-xs"
            )

    def _start():
        limit = batch.value or None  # 0 = all
        if not worker.start(limit):
            ui.notify("The saver is already running.", type="warning")

    async def refresh():
        try:
            c = await run.io_bound(services.with_db, database.status_counts)
        except (sqlite3.Error, OSError) as e:  # e.g. the database's drive is not connected
            message.set_text(f"Cannot read the database: {e}")
            return
        saved.set_text(f"{c['saved']:,}")
        of_total.set_text(f"/ {c['total']:,}")
        for label, key in (
            (total, "total"),
            (pending, "pending"),
            (failed, "failed"),
            (unavailable, "unavailable"),
            (skipped, "skipped"),
        ):
            label.set_text(f"{c[key]:,}")
        share = percent_done(c)
        percent.set_text(f"{share:.1%}")
        failed_share = c["failed"] / c["total"] if c["total"] else 0
        ruler.set_content(ruler_html(share, failed_share))
        midpoint.set_text(f"{c['total'] // 2:,}")
        end.set_text(f"{c['total']:,}")

        badge.show(worker.state)
        start.set_enabled(not worker.busy)
        stop.set_enabled(worker.state == "running")
        batch.set_enabled(not worker.busy)
        message.set_text(worker.message or ("Ready." if not worker.busy else "Saving…"))

        s = worker.stats
        details.set_visibility(s is not None)
        idle_note.set_visibility(s is None)
        if s is None:
            return
        m = metrics(s, c["pending"], worker.limit)
        if s.current:
            current.set_text(post_url(s.current))
            current.props(f"href={post_url(s.current)}")
        elif not worker.busy:
            current.set_text("Run finished")
        processed.set_text(f"{s.processed:,}")
        newly.set_text(f"{s.outcomes['saved']:,}")
        already.set_text(f"{s.outcomes['already_saved']:,}")
        failures.set_text(f"{s.errors:,}")
        elapsed.set_text(hms(m["elapsed"]))
        avg.set_text(f"{m['avg']:.1f}" if m["avg"] else "–")
        per_hour.set_text(f"{m['per_hour']:.0f}" if m["per_hour"] else "–")
        remaining.set_text(f"{m['remaining']:,}")
        eta.set_text(hms(m["eta"]) if m["avg"] and worker.busy else "–")

    ui.timer(1.0, refresh)
