"""Archive search over the liked/saved export manifests. Local only; Instagram is never opened."""

from datetime import datetime

from nicegui import run, ui

from src import services
from src.instagram.export import search_posts, snippet
from src.ui.components.layout import frame

SOURCES = {"all": "All", "liked": "Liked", "saved": "Saved"}
PAGE_SIZES = (25, 50, 100, 200)
DEFAULT_PAGE_SIZE = 100


def find(source: str, query: str) -> list[dict]:
    sources = ["liked", "saved"] if source == "all" else [source]
    return search_posts(services.load_posts(services.manifest_paths(), sources), query)


class SearchView:
    """One tab's search: the complete, newest-first match list and which page of it is shown.

    Every match is kept; only the current page is rendered. Result numbers are global, so the
    first card of page 2 at 100 per page is number 101.
    """

    def __init__(self, finder=find):
        self._find = finder
        self.query = ""
        self.source = "all"
        self.page_size = DEFAULT_PAGE_SIZE
        self.page = 1
        self.hits: list[dict] = []

    def search(self, query: str, source: str | None = None) -> None:
        """Run a search: a new query or a new All / Liked / Saved choice. Always page 1."""
        self.query = query.strip()
        self.source = source or self.source
        self.hits = self._find(self.source, self.query) if self.query else []
        self.page = 1

    def set_page_size(self, size: int) -> None:
        self.page_size = size
        self.page = 1

    @property
    def pages(self) -> int:
        return max(1, -(-len(self.hits) // self.page_size))

    def go(self, page: int) -> None:
        self.page = min(max(page, 1), self.pages)

    @property
    def start(self) -> int:
        """Index into hits of the current page's first result."""
        return (self.page - 1) * self.page_size

    def rows(self) -> list[tuple[int, dict]]:
        """(global result number from 1, record) for the current page only."""
        page = self.hits[self.start : self.start + self.page_size]
        return list(enumerate(page, start=self.start + 1))

    def summary(self) -> list[str]:
        n = len(self.hits)
        if not n:
            return [f"No results for “{self.query}”"]
        last = min(self.start + self.page_size, n)
        return [
            f"{n:,} result{'s' * (n != 1)} for “{self.query}”",
            f"Showing {self.start + 1:,}–{last:,} of {n:,}",
            f"Page {self.page} of {self.pages}",
        ]


def page_links(current: int, total: int) -> list[int | None]:
    """Page numbers for the pager; None marks a gap ("...").

    Short ranges list every page. Otherwise: the first and last page, and a window of five
    around the current one, e.g. 1 2 3 4 5 ... 12 or 1 ... 6 7 8 9 10 ... 20.
    """
    if total <= 9:
        return list(range(1, total + 1))
    start, end = max(current - 2, 1), min(current + 2, total)
    if current <= 4:
        start, end = 1, 5
    elif current >= total - 3:
        start, end = total - 4, total
    shown = sorted({1, total, *range(start, end + 1)})
    links: list[int | None] = []
    for page in shown:
        if links and page - links[-1] == 2:
            links.append(page - 1)  # a single hidden page is shown rather than "..."
        elif links and page - links[-1] > 2:
            links.append(None)
        links.append(page)
    return links


def result_card(number: int, r: dict, query: str) -> None:
    """One result row: its global number on the left, then source, date, owner and caption."""
    when = datetime.fromisoformat(r["timestamp"]).astimezone()
    kind = "Reel" if r["post_type"] == "reel" else "Post"
    with ui.row().classes("result w-full no-wrap gap-0"):
        ui.label(f"{number:,}").classes("result-number")
        with ui.column().classes("grow min-w-0 gap-2 py-4 pl-5 pr-4"):
            with ui.row().classes("w-full items-center gap-2"):
                liked = r["source"] == "liked"
                ui.label(r["source"].upper()).classes("chip" + (" chip-accent" if liked else ""))
                ui.label(kind.upper()).classes("chip")
                ui.label(f"{when:%d %b %Y, %H:%M}").classes("mono text-xs muted")
                ui.space()
                ui.button(
                    f"Open {kind}",
                    icon="north_east",
                    color=None,
                    on_click=lambda url=r["url"]: ui.navigate.to(url, new_tab=True),
                ).classes("pill btn-quiet text-xs").props("flat dense")
            with ui.row().classes("items-baseline gap-x-2 gap-y-0"):
                if r["username"]:
                    ui.label("@" + r["username"]).classes("font-semibold")
                if r["owner_name"]:
                    ui.label(r["owner_name"]).classes("muted")
            if r["caption"]:
                ui.label(snippet(r["caption"], query)).classes("text-sm break-words")
            ui.link(r["url"], r["url"], new_tab=True).classes("mono text-xs faint break-all")


CSS = """
.result-number { min-width: 4.75rem; padding: 18px 14px 0; text-align: right;
  font-family: var(--mono); font-size: 18px; color: var(--text);
  font-variant-numeric: tabular-nums; border-right: 1px solid var(--line-soft); }
@media (max-width: 600px) {
  .result-number { min-width: 3rem; padding: 18px 10px 0; font-size: 15px; }
}
.result:hover { background: var(--panel-2); }
.result a { text-decoration: none; }
.page-btn { font-family: var(--mono); min-width: 2.1rem; border-radius: 999px !important;
  color: var(--muted); }
"""


@ui.page("/search")
def search_page():
    view = SearchView()
    ui.add_css(CSS)

    def pager(where: str):
        if view.pages == 1:
            return
        with ui.row().classes(f"{where} w-full items-center justify-center gap-1"):

            def nav(icon, label, page, enabled):
                button = ui.button(icon=icon, on_click=lambda: turn(page))
                button.props("flat dense round color=grey-5").tooltip(label)
                button.set_enabled(enabled)

            nav("first_page", "First page", 1, view.page > 1)
            nav("chevron_left", "Previous", view.page - 1, view.page > 1)
            for page in page_links(view.page, view.pages):
                if page is None:
                    ui.label("…").classes("faint px-1")
                elif page == view.page:
                    ui.button(str(page), color=None).classes("page-btn btn-primary").props(
                        "unelevated dense"
                    )
                else:
                    ui.button(str(page), color=None, on_click=lambda p=page: turn(p)).classes(
                        "page-btn btn-ghost"
                    ).props("flat dense")
            nav("chevron_right", "Next", view.page + 1, view.page < view.pages)
            nav("last_page", "Last page", view.pages, view.page < view.pages)

    @ui.refreshable
    def results():
        if not view.query:
            ui.label("Search captions, hashtags, usernames and owner names.").classes("muted")
            return
        with ui.element("div").classes("panel w-full divide overflow-hidden"):
            with ui.row().classes("panel-head w-full items-center gap-x-6 gap-y-2"):
                first, *rest = view.summary()
                ui.label(first).classes("font-semibold")
                for line in rest:
                    ui.label(line).classes("eyebrow")
            pager("py-3")
            for number, r in view.rows():
                result_card(number, r, view.query)
            pager("py-3")

    async def run_search(action, *args):
        try:
            await run.io_bound(action, *args)
        except FileNotFoundError as e:
            ui.notify(
                f"{e} (or use Exports > Rebuild Search Index)", type="warning", multi_line=True
            )
            return
        results.refresh()

    async def go():
        await run_search(view.search, query.value or "", source.value)

    def turn(page: int):
        view.go(page)
        results.refresh()
        ui.run_javascript("window.scrollTo(0, 0)")

    def resize(e):
        view.set_page_size(e.value)
        results.refresh()

    with frame("Search", "/search"):
        with (
            ui.element("div").classes("panel w-full panel-body"),
            ui.row().classes("w-full items-center gap-3"),
        ):
            source = ui.toggle(SOURCES, value=view.source).classes("segmented")
            source.props("unelevated no-caps dense toggle-color=grey-3 toggle-text-color=black")
            query = ui.input(
                placeholder='Caption, #hashtag, @username or owner, e.g. "harry potter"'
            )
            query.classes("grow min-w-[240px]").props("outlined dense clearable autofocus")
            ui.button("Search", color=None, on_click=lambda: go()).classes(
                "pill btn-primary"
            ).props("unelevated")
            size = ui.select({n: f"{n} per page" for n in PAGE_SIZES}, value=view.page_size).props(
                "dense outlined options-dense"
            )
        results()

    query.on("keydown.enter", go)
    source.on_value_change(lambda e: run_search(view.search, query.value or "", e.value))
    size.on_value_change(resize)
