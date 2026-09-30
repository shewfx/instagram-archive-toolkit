"""Paging of the UI's search results. Uses the real matching; only the records are generated."""

import pytest

from src.instagram.export import search_posts
from src.ui.pages.search import DEFAULT_PAGE_SIZE, SearchView, page_links


def record(source, i, caption):
    return {
        "source": source,
        "url": f"https://www.instagram.com/{'reel' if i % 2 else 'p'}/{source}{i}/",
        "shortcode": f"{source}{i}",
        "post_type": "reel" if i % 2 else "post",
        "caption": caption,
        "hashtags": [],
        "owner_name": None,
        "username": f"user{i}",
        # Distinct, zero-padded minutes: a larger i is newer.
        "timestamp": f"2026-01-01T{i // 60:02}:{i % 60:02}:00+00:00",
    }


# 347 liked and 60 saved matches for "gym", plus records that must never match.
RECORDS = {
    "liked": [record("liked", i, f"Gym day {i}") for i in range(347)]
    + [record("liked", 1000 + i, "rest day") for i in range(5)],
    "saved": [record("saved", i, f"gym tips {i}") for i in range(60)],
}


def finder(source, query):
    sources = ["liked", "saved"] if source == "all" else [source]
    return search_posts([r for s in sources for r in RECORDS[s]], query)


@pytest.fixture
def view():
    v = SearchView(finder)
    v.search("gym", "liked")
    return v


def numbers(view):
    return [n for n, _ in view.rows()]


def test_every_match_is_kept_and_counted(view):
    assert DEFAULT_PAGE_SIZE == 100
    assert len(view.hits) == 347
    assert view.pages == 4
    assert view.summary() == [
        "347 results for “gym”",
        "Showing 1–100 of 347",
        "Page 1 of 4",
    ]


def test_page_1_is_numbered_1_to_100_newest_first(view):
    rows = view.rows()
    assert numbers(view) == list(range(1, 101))
    assert rows[0][1]["caption"] == "Gym day 346"  # newest first
    assert rows[-1][1]["caption"] == "Gym day 247"


def test_page_2_continues_the_numbering_and_the_order(view):
    view.go(2)
    assert numbers(view) == list(range(101, 201))
    assert view.rows()[0][1]["caption"] == "Gym day 246"
    assert view.summary()[1:] == ["Showing 101–200 of 347", "Page 2 of 4"]


def test_final_partial_page(view):
    view.go(4)
    assert numbers(view) == list(range(301, 348))
    assert view.rows()[-1][1]["caption"] == "Gym day 0"
    assert view.summary()[1:] == ["Showing 301–347 of 347", "Page 4 of 4"]


def test_pages_together_are_the_whole_result_in_order(view):
    seen = []
    for page in range(1, view.pages + 1):
        view.go(page)
        seen += [r for _, r in view.rows()]
    assert seen == view.hits
    assert [r["timestamp"] for r in seen] == sorted((r["timestamp"] for r in seen), reverse=True)


def test_previous_next_first_last_stay_in_range(view):
    view.go(view.page + 1)  # Next
    assert view.page == 2
    view.go(view.page - 1)  # Previous
    assert view.page == 1
    view.go(view.page - 1)  # Previous on the first page
    assert view.page == 1
    view.go(view.pages)  # Last
    assert view.page == 4
    view.go(view.page + 1)  # Next on the last page
    assert view.page == 4
    view.go(1)  # First
    assert view.page == 1


def test_new_search_resets_to_page_1(view):
    view.go(3)
    view.search("day")
    assert (view.page, len(view.hits)) == (1, 352)
    assert numbers(view)[0] == 1


def test_source_change_resets_to_page_1(view):
    view.go(3)
    view.search("gym", "all")
    assert (view.page, view.source, len(view.hits)) == (1, "all", 407)
    view.go(5)
    view.search("gym", "saved")
    assert (view.page, len(view.hits), view.pages) == (1, 60, 1)
    assert {r["source"] for r in view.hits} == {"saved"}


def test_page_size_change_resets_to_page_1(view):
    view.go(3)
    view.set_page_size(25)
    assert (view.page, view.pages) == (1, 14)
    view.go(14)
    assert numbers(view) == list(range(326, 348))
    view.set_page_size(200)
    assert (view.page, view.pages, numbers(view)[-1]) == (1, 2, 200)


def test_no_results(view):
    view.search("zzz nothing")
    assert view.hits == [] and view.rows() == []
    assert (view.page, view.pages) == (1, 1)
    assert view.summary() == ["No results for “zzz nothing”"]


def test_exactly_one_full_page():
    v = SearchView(lambda _s, _q: [{"n": i} for i in range(100)])
    v.search("x")
    assert v.pages == 1 and numbers(v) == list(range(1, 101))


@pytest.mark.parametrize(
    ("current", "total", "expected"),
    [
        (1, 1, [1]),
        (3, 9, [1, 2, 3, 4, 5, 6, 7, 8, 9]),
        (1, 12, [1, 2, 3, 4, 5, None, 12]),
        (4, 12, [1, 2, 3, 4, 5, None, 12]),
        (5, 12, [1, 2, 3, 4, 5, 6, 7, None, 12]),  # 2 is shown, not "1 ... 3"
        (8, 20, [1, None, 6, 7, 8, 9, 10, None, 20]),
        (12, 12, [1, None, 8, 9, 10, 11, 12]),
        (6, 10, [1, None, 4, 5, 6, 7, 8, 9, 10]),  # 9 is shown, not "8 ... 10"
    ],
)
def test_page_links_condense_long_ranges(current, total, expected):
    assert page_links(current, total) == expected
