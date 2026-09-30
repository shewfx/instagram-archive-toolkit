"""Local settings, stored in data/settings.json. Paths and pacing only: no cookies or sessions."""

from nicegui import ui

from src import config
from src.ui.components.layout import frame
from src.ui.state import worker

# key -> (label, hint)
FIELDS = {
    "LIKED_HTML": ("Liked HTML path", ".../your_instagram_activity/likes/liked_posts.html"),
    "SAVED_HTML": ("Saved HTML path", ".../your_instagram_activity/saved/saved_posts.html"),
    "DB_PATH": ("SQLite database path", "Progress of the saver"),
    "PROFILE_DIR": ("Browser profile folder", "Chrome profile holding the Instagram login"),
    "ITEM_DELAY": (
        "Pause per Reel (seconds)",
        f"Minimum {config.MIN_ITEM_DELAY:g}. Raise it to go slower; it cannot go faster.",
    ),
    "BATCH_SIZE": ("Default batch size", "Preselected in the saver's Process menu"),
}


@ui.page("/settings")
def settings_page():
    current = config.current_settings()
    inputs = {}
    with frame("Settings", "/settings"), ui.element("div").classes("panel w-full divide"):
        # One row per setting: name and explanation on the left, the value on the right.
        for key, (label, hint) in FIELDS.items():
            value = current[key]
            with ui.grid().classes("panel-body w-full gap-x-6 gap-y-2 grid-cols-1 md:grid-cols-5"):
                with ui.column().classes("gap-1 md:col-span-2"):
                    ui.label(label).classes("font-medium")
                    ui.label(hint).classes("muted text-xs")
                if key in ("ITEM_DELAY", "BATCH_SIZE"):
                    step = 0.5 if key == "ITEM_DELAY" else 1
                    minimum = config.MIN_ITEM_DELAY if key == "ITEM_DELAY" else 1
                    field = ui.number(value=value, min=minimum, step=step)
                else:
                    field = ui.input(value=value or "")
                inputs[key] = field.props("outlined dense").classes("md:col-span-3 mono")
                field.props(f'aria-label="{label}"')
        with ui.row().classes("panel-body w-full items-center gap-3"):
            save = ui.button("Save settings", color=None, on_click=lambda: _save()).classes(
                "pill btn-primary"
            )
            save.props("unelevated")
            ui.label(
                "The CLI reads the same file. Database and profile changes apply to the next "
                "saver run."
            ).classes("muted text-xs grow")
            ui.label(str(config.SETTINGS_PATH)).classes("mono text-xs faint")

    def _save():
        if worker.busy:
            ui.notify("Stop the saver before changing settings.", type="warning")
            return
        values = {k: (f.value if f.value is not None else "") for k, f in inputs.items()}
        if values["BATCH_SIZE"] != "":
            values["BATCH_SIZE"] = int(values["BATCH_SIZE"])
        try:
            config.save_settings(values)
        except (ValueError, TypeError) as e:
            ui.notify(f"Not saved: {e}", type="negative")
            return
        ui.notify("Settings saved.", type="positive")

    ui.timer(1.0, lambda: save.set_enabled(not worker.busy))
