"""Failed Reels: inspect, reset to pending or skip."""

from nicegui import run, ui

from src import database, services
from src.ui.components.layout import frame


@ui.page("/failed")
def failed_page():
    with frame("Failed items", "/failed"), ui.element("div").classes("panel w-full divide"):
        with ui.row().classes("panel-head w-full items-center gap-3"):
            count = ui.label().classes("stat-number red")
            ui.label("failed Reels").classes("muted")
            ui.space()
            reset_all = (
                ui.button(
                    "Reset all failed to pending", color=None, on_click=lambda: confirm.open()
                )
                .classes("pill btn-quiet")
                .props("flat")
            )
        rows = ui.column().classes("w-full gap-0 divide")

    with ui.dialog() as confirm, ui.element("div").classes("panel panel-body w-[380px] max-w-full"):
        confirm_text = ui.label().classes("text-base")
        ui.label("Their error history is kept.").classes("muted text-sm pt-1")
        with ui.row().classes("w-full justify-end gap-2 pt-4"):
            ui.button("Cancel", color=None, on_click=confirm.close).classes("pill btn-quiet").props(
                "flat"
            )
            ui.button("Reset all", color=None, on_click=lambda: reset_everything()).classes(
                "pill btn-primary"
            ).props("unelevated")

    async def act(fn, *args, note: str):
        await run.io_bound(services.with_db, fn, *args)
        ui.notify(note)
        await render()

    async def reset_everything():
        confirm.close()
        n = await run.io_bound(services.with_db, database.reset_failed)
        ui.notify(f"{n} Reels set back to pending.")
        await render()

    async def render():
        failed = await run.io_bound(services.with_db, database.list_failed)
        count.set_text(f"{len(failed):,}")
        confirm_text.set_text(f"Set all {len(failed):,} failed Reels back to pending?")
        reset_all.set_enabled(bool(failed))
        rows.clear()
        with rows:
            if not failed:
                ui.label("Nothing has failed.").classes("muted panel-body")
            for r in failed:
                code, url = r["shortcode"], r["reel_url"]
                with ui.row().classes("panel-body w-full items-center gap-4"):
                    with ui.column().classes("gap-1 grow min-w-0"):
                        with ui.row().classes("items-baseline gap-3"):
                            ui.label(code).classes("mono font-semibold")
                            ui.link(url, url, new_tab=True).classes("mono text-xs faint break-all")
                        ui.label(r["last_error"] or "No error recorded").classes(
                            "red text-sm break-words"
                        )
                        attempts = f"{r['attempts']} attempt{'s' * (r['attempts'] != 1)}"
                        ui.label(f"Processed {r['processed_at'] or 'unknown'}, {attempts}").classes(
                            "mono text-xs muted"
                        )
                    with ui.row().classes("items-center gap-2"):
                        ui.button(
                            icon="north_east",
                            on_click=lambda u=url: ui.navigate.to(u, new_tab=True),
                        ).props("flat round dense color=grey-5").tooltip("Open")
                        ui.button(
                            "Reset to pending",
                            color=None,
                            on_click=lambda c=code: act(
                                database.set_status, c, "pending", note=f"{c} is pending again."
                            ),
                        ).classes("pill btn-quiet text-xs").props("flat dense")
                        ui.button(
                            "Mark skipped",
                            color=None,
                            on_click=lambda c=code: act(
                                database.set_status, c, "skipped", note=f"{c} skipped."
                            ),
                        ).classes("pill btn-ghost text-xs").props("flat dense")

    ui.timer(0, render, once=True)
