"""Live saver output, and earlier runs' log files from data/logs/ (read-only)."""

from nicegui import run, ui

from src import config
from src.ui.components.layout import frame
from src.ui.state import worker

# Only the end of long log files is shown.
TAIL_LINES = 5000


def log_files() -> list[str]:
    if not config.LOG_DIR.exists():
        return []
    return sorted((p.name for p in config.LOG_DIR.glob("*.log")), reverse=True)


def read_tail(name: str) -> str:
    if name not in log_files():  # only files listed from LOG_DIR, never an arbitrary path
        raise ValueError(f"not a log file: {name}")
    lines = (config.LOG_DIR / name).read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-TAIL_LINES:])


def log_box():
    with ui.scroll_area().classes("w-full h-[60vh]") as area:
        text = ui.label().classes("mono text-xs whitespace-pre-wrap px-5 py-4 leading-relaxed")
    return area, text


@ui.page("/logs")
def logs_page():
    with frame("Logs", "/logs"), ui.element("div").classes("panel w-full divide overflow-hidden"):
        tabs = ui.tabs().props("no-caps dense align=left indicator-color=primary")
        with tabs.classes("panel-head w-full muted").props("active-color=white"):
            live_tab = ui.tab("Live saver output")
            files_tab = ui.tab("Previous runs")
        with ui.tab_panels(tabs, value=live_tab).classes("w-full bg-transparent"):
            with ui.tab_panel(live_tab).classes("p-0 gap-0 divide"):
                with ui.row().classes("w-full px-5 py-2 items-center"):
                    ui.label("Saver output since the UI started").classes("eyebrow")
                    ui.space()
                    autoscroll = ui.switch("Auto-scroll", value=True).props("dense")
                live_area, live_text = log_box()
            with ui.tab_panel(files_tab).classes("p-0 gap-0 divide"):
                with ui.row().classes("w-full px-5 py-3 items-center gap-3"):
                    ui.label("Log file").classes("eyebrow")
                    picker = ui.select(log_files()).props("outlined dense")
                    picker.classes("min-w-[300px] mono")
                _, file_text = log_box()

    seen = -1

    def refresh_live():
        nonlocal seen
        if worker.line_count == seen:
            return
        seen = worker.line_count
        lines = "\n".join(worker.lines)
        live_text.set_text(lines or "No saver run since the UI started.")
        live_text.classes(add=None if lines else "muted", remove="muted" if lines else None)
        if autoscroll.value:
            live_area.scroll_to(percent=1.0)

    async def show_file(e):
        if e.value:
            file_text.set_text(await run.io_bound(read_tail, e.value))

    picker.on_value_change(show_file)
    tabs.on_value_change(lambda: picker.set_options(log_files(), value=picker.value))
    ui.timer(1.0, refresh_live)
