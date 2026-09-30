"""Instagram export files and the search index built from them."""

from pathlib import Path

from nicegui import run, ui

from src import config, services
from src.ui.components.layout import frame


def sources() -> list[tuple[str, Path | None, Path]]:
    """(source, configured HTML path, manifest path)."""
    manifests = services.manifest_paths()
    return [
        ("liked", config.LIKED_HTML, manifests["liked"]),
        ("saved", config.SAVED_HTML, manifests["saved"]),
    ]


def overview() -> list[tuple[str, Path | None, bool, dict | None]]:
    """(source, HTML path, whether it exists, manifest info). Reads files: run off the loop."""
    return [
        (source, html, bool(html and html.exists()), services.manifest_info(manifest))
        for source, html, manifest in sources()
    ]


def rebuild() -> list[str]:
    """Same work as `build-search --liked ... --saved ...`, for each configured file that exists."""
    done = []
    for source, html, manifest in sources():
        if html and html.exists():
            records = services.build_index(source, html, manifest)
            done.append(f"{source}: {len(records):,}")
    return done


@ui.page("/exports")
def exports_page():
    with frame("Exports", "/exports"):
        cards = ui.grid().classes("w-full gap-4 grid-cols-1 md:grid-cols-2")
        with ui.row().classes("items-center gap-3"):
            button = ui.button("Rebuild Search Index", color=None, on_click=lambda: go()).classes(
                "pill btn-primary"
            )
            button.props("unelevated")
            ui.label("Paths are set on the Settings page.").classes("muted text-sm")

    async def render():
        rows = await run.io_bound(overview)
        cards.clear()
        with cards:
            for source, html, exists, info in rows:
                with ui.element("div").classes("panel divide"):
                    with ui.row().classes("panel-head w-full items-center"):
                        ui.label(f"{source.capitalize()} posts").classes("font-semibold")
                        ui.space()
                        with ui.row().classes(
                            f"status-pill items-center gap-2 no-wrap {'accent' if exists else 'red'}"
                        ):
                            ui.element("div").classes("status-dot")
                            ui.label("File found" if exists else "File missing")
                    with ui.column().classes("panel-body w-full gap-4"):
                        with ui.grid(columns=2).classes("w-full gap-4"):
                            for label, value in (
                                ("Entries", f"{info['entries']:,}" if info else "–"),
                                ("Reels", f"{info['reels']:,}" if info else "–"),
                            ):
                                with ui.column().classes("gap-1"):
                                    ui.label(value).classes("stat-number")
                                    ui.label(label).classes("muted text-xs")
                        with ui.column().classes("gap-1"):
                            ui.label("Source file").classes("eyebrow")
                            ui.label(str(html) if html else "Not configured").classes(
                                "mono text-xs muted break-all"
                            )
                    with ui.row().classes("panel-body w-full items-center justify-between"):
                        ui.label("Index built").classes("eyebrow")
                        ui.label(
                            f"{info['built_at']:%d %b %Y, %H:%M}" if info else "Never"
                        ).classes("mono text-sm")

    async def go():
        button.props("loading")
        try:
            done = await run.io_bound(rebuild)
        except (OSError, ValueError, AttributeError) as e:  # unreadable or unexpected HTML
            ui.notify(f"Rebuild failed: {e}", type="negative", multi_line=True)
        else:
            if done:
                ui.notify("Search index rebuilt. " + ", ".join(done) + " posts.", type="positive")
            else:
                ui.notify("No configured export file exists. Check Settings.", type="warning")
        finally:
            button.props(remove="loading")
        await render()

    ui.timer(0, render, once=True)
