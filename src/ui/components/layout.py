"""Page frame shared by every screen: thin header with the saver status, side navigation."""

from contextlib import contextmanager

from nicegui import ui

from src.ui.components.widgets import status_badge
from src.ui.state import worker

NAV = [
    ("/", "Dashboard", "space_dashboard"),
    ("/search", "Search", "search"),
    ("/failed", "Failed items", "error_outline"),
    ("/exports", "Exports", "inventory_2"),
    ("/settings", "Settings", "tune"),
    ("/logs", "Logs", "receipt_long"),
]

# Design tokens. One accent (lime) for "done" and the primary action; amber and red only for
# pending/warning and failure. Fonts ship with Windows 11, so nothing is fetched from the web.
CSS = """
:root {
  --bg: #0b0c0e; --panel: #151619; --panel-2: #1b1c20; --line: #26272c; --line-soft: #1f2024;
  --text: #ececec; --muted: #8a8e97; --faint: #5a5e66;
  --accent: #c8f031; --accent-ink: #151a02; --amber: #f2b441; --red: #ef6b6b;
  --sans: "Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;
  --mono: "Cascadia Mono", "Cascadia Code", Consolas, ui-monospace, monospace;
}
body, .q-page-container, .q-layout { background: var(--bg); color: var(--text);
  font-family: var(--sans); font-size: 14px; }
.q-header { background: var(--bg) !important; border-bottom: 1px solid var(--line-soft);
  color: var(--text); }
.q-drawer { background: var(--bg) !important; border-right: 1px solid var(--line-soft) !important; }
.q-drawer--mobile { background: var(--panel) !important; }

/* Surfaces */
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 16px;
  box-shadow: none; }
.panel-head { padding: 14px 20px; border-bottom: 1px solid var(--line-soft); }
.panel-body { padding: 18px 20px; }
.divide > * + * { border-top: 1px solid var(--line-soft); }

/* Type */
.mono { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.eyebrow { font-family: var(--mono); font-size: 11px; letter-spacing: .12em;
  text-transform: uppercase; color: var(--muted); }
.page-title { font-family: "Segoe UI Variable Display", "Segoe UI Variable", "Segoe UI",
  system-ui, sans-serif; font-size: 23px; font-weight: 650; line-height: 1.15;
  letter-spacing: -.015em; color: #fff; }
.big-number { font-family: var(--mono); font-size: 40px; line-height: 1; letter-spacing: -.02em;
  font-variant-numeric: tabular-nums; }
.stat-number { font-family: var(--mono); font-size: 22px; line-height: 1.15;
  font-variant-numeric: tabular-nums; }

/* Navigation */
.nav-link { position: relative; border-radius: 10px; color: var(--muted);
  text-decoration: none; }
.nav-link:hover { color: var(--text); background: var(--line-soft); }
.nav-link.active { color: var(--text); background: var(--panel); }
.nav-link.active::before { content: ""; position: absolute; left: -8px; top: 9px; bottom: 9px;
  width: 3px; border-radius: 3px; background: var(--accent); }
.nav-link:focus-visible, .q-btn:focus-visible { outline: 2px solid var(--accent);
  outline-offset: 2px; }

/* Controls. .q-btn doubles the specificity so these beat Quasar's bg-primary/text-white. */
.pill { border-radius: 999px !important; padding: 4px 16px !important; font-weight: 500; }
.q-btn.btn-primary { background: var(--accent) !important; color: var(--accent-ink) !important; }
.q-btn.btn-quiet { background: var(--panel-2) !important; color: var(--text) !important;
  border: 1px solid var(--line); }
.q-btn.btn-ghost { background: transparent !important; color: var(--muted) !important; }
.q-btn.btn-ghost:hover { color: var(--text) !important; }
.q-btn.disabled { opacity: .35 !important; }
.chip { font-family: var(--mono); font-size: 10.5px; letter-spacing: .1em; padding: 2px 8px;
  border-radius: 6px; border: 1px solid var(--line); color: var(--muted); }
.chip-accent { color: var(--accent); border-color: rgba(200, 240, 49, .35);
  background: rgba(200, 240, 49, .06); }
.status-pill { font-family: var(--mono); font-size: 11px; letter-spacing: .08em;
  text-transform: uppercase; padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--line); background: var(--panel); color: var(--muted); }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

/* Quasar inputs in the panel palette */
.q-field--outlined .q-field__control { border-radius: 10px; background: var(--panel-2); }
.q-field--outlined .q-field__control:before { border-color: var(--line) !important; }
.q-field__native, .q-field__input, .q-select__dropdown-icon { color: var(--text) !important; }
.q-field__label, .q-field__bottom { color: var(--muted) !important; }
.q-menu { background: var(--panel-2); color: var(--text); border: 1px solid var(--line); }
.q-toggle__inner--truthy { color: var(--accent) !important; }

/* Segmented toggle (sources, batch sizes) */
.segmented { background: var(--panel-2); border: 1px solid var(--line); border-radius: 999px;
  padding: 2px; }
.segmented .q-btn { border-radius: 999px !important; color: var(--muted);
  font-family: var(--mono); font-size: 12px; min-height: 28px; padding: 0 12px; }
.segmented .q-btn[aria-pressed="true"] { background: var(--text) !important;
  color: var(--bg) !important; }

/* Tick ruler: the dashboard's progress bar */
.ruler { display: flex; align-items: flex-end; justify-content: space-between; height: 28px; }
.tick { flex: 0 0 2px; height: 12px; border-radius: 1px; background: #3a3c43; }
.tick.major { height: 20px; background: #45474e; }
.tick.done { background: var(--accent); }
.tick.fail { background: var(--red); }
.ruler-marker { position: absolute; bottom: 0; width: 2px; height: 28px; background: var(--text);
  border-radius: 1px; }

/* Color utilities last, so they override component defaults. */
.muted { color: var(--muted); }
.faint { color: var(--faint); }
.accent { color: var(--accent) !important; }
.amber { color: var(--amber) !important; }
.red { color: var(--red) !important; }
"""


@contextmanager
def frame(title: str, path: str):
    """Build the shared chrome, then yield inside the page's content column."""
    ui.add_css(CSS)
    ui.colors(primary="#c8f031", positive="#c8f031", negative="#ef6b6b", warning="#f2b441")
    with ui.header().classes("items-center px-5 py-3 gap-3"):
        ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
            "flat round dense color=grey-5"
        ).classes("lt-md")
        with ui.row().classes("items-center gap-2"):
            ui.element("div").classes("status-dot accent")
            ui.label("Insta Archive").classes("font-semibold tracking-tight")
        ui.space()
        badge = status_badge()
        ui.timer(1.0, lambda: badge.show(worker.state))
    with (
        ui.left_drawer().props("width=200 breakpoint=900") as drawer,
        ui.column().classes("w-full gap-1 px-4 py-5"),
    ):
        for href, label, icon in NAV:
            active = " active" if href == path else ""
            with (
                ui.link(target=href).classes(f"nav-link{active} w-full"),
                ui.row().classes("items-center gap-3 px-3 py-2 no-wrap"),
            ):
                ui.icon(icon, size="18px")
                ui.label(label)
    with ui.column().classes("w-full max-w-5xl mx-auto px-4 py-6 gap-4"):
        ui.label(title).classes("page-title")
        yield
