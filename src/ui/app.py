"""NiceGUI control panel. Local only: listens on 127.0.0.1."""

from nicegui import app, ui

from src import config
from src.ui.pages import dashboard, exports, failed, logs, search, settings  # noqa: F401  (routes)
from src.ui.state import worker

PORT = 8080


def _shutdown() -> None:
    # Ctrl+C on the server: finish the Reel in progress (its outcome is committed), then stop.
    worker.stop()
    worker.join(timeout=3 * config.NAV_TIMEOUT)


app.on_shutdown(_shutdown)
ui.button.default_props("no-caps")


def main() -> None:
    ui.run(
        title="Insta Archive",
        host="127.0.0.1",
        port=PORT,
        dark=True,
        reload=False,  # a reloader would import this twice: two saver workers
        show=False,
        favicon="🗂️",
    )
