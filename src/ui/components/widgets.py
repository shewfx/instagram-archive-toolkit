"""Small building blocks reused across pages."""

from nicegui import ui

# Saver state -> (label, text color class).
STATES = {
    "idle": ("Idle", "muted"),
    "running": ("Running", "accent"),
    "stopping": ("Stopping", "amber"),
    "stopped": ("Stopped: warning/error", "red"),
}

TICKS = 64
MAJOR_EVERY = 8


class StatusBadge(ui.row):
    """A pill with a colored dot: the saver's state."""

    def __init__(self):
        super().__init__()
        self.classes("status-pill items-center gap-2 no-wrap")
        with self:
            self.dot = ui.element("div").classes("status-dot")
            self.label = ui.label()

    def show(self, state: str) -> None:
        text, color = STATES[state]
        self.label.set_text(text)
        self.classes(remove=" ".join(c for _, c in STATES.values()), add=color)


def status_badge(state: str = "idle") -> StatusBadge:
    badge = StatusBadge()
    badge.show(state)
    return badge


def stat(label: str, color: str = "") -> ui.label:
    """Big number over a small label, for a stat strip. Returns the number label."""
    with ui.column().classes("gap-1 min-w-0"):
        value = ui.label("–").classes(f"stat-number {color}")
        ui.label(label).classes("muted text-xs")
    return value


def field(label: str) -> ui.label:
    """A small uppercase label over a value, for run details. Returns the value label."""
    with ui.column().classes("gap-1 min-w-0"):
        ui.label(label).classes("eyebrow")
        return ui.label("–").classes("mono text-base")


def ruler_html(done: float, failed: float, ticks: int = TICKS) -> str:
    """The tick ruler: `done` share in lime, then `failed` share in red, the rest dim.

    Built only from numbers, so it is safe to render unsanitized.
    """
    done_n = round(done * ticks)
    fail_n = max(round(failed * ticks), 1 if failed > 0 else 0)
    cells = []
    for i in range(ticks):
        kind = " done" if i < done_n else " fail" if i < done_n + fail_n else ""
        major = " major" if i % MAJOR_EVERY == 0 or i == ticks - 1 else ""
        cells.append(f'<div class="tick{major}{kind}"></div>')
    marker = f'<div class="ruler-marker" style="left: calc({done:.4%} - 1px)"></div>'
    return f'<div class="relative"><div class="ruler">{"".join(cells)}</div>{marker}</div>'
