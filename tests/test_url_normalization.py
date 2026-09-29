import pytest

from src.instagram.urls import parse_post_url, post_url


@pytest.mark.parametrize(
    "href, expected",
    [
        ("/reel/C8abc_-12/", ("reel", "C8abc_-12")),
        ("/reel/C8abc_-12", ("reel", "C8abc_-12")),
        ("/reels/C8abc/", ("reel", "C8abc")),
        ("/p/C8abc/", ("p", "C8abc")),
        ("/some.user_1/reel/C8abc/", ("reel", "C8abc")),
        (
            "https://www.instagram.com/reel/C8abc/?utm_source=ig_web_copy_link&igsh=x",
            ("reel", "C8abc"),
        ),
        ("https://instagram.com/reel/C8abc/#comments", ("reel", "C8abc")),
        ("http://www.instagram.com/p/C8abc", ("p", "C8abc")),
    ],
)
def test_parses_post_and_reel_links(href, expected):
    assert parse_post_url(href) == expected


@pytest.mark.parametrize(
    "href",
    [
        None,
        "",
        "/",
        "/explore/",
        "/reels/",  # the Reels feed, not a reel
        "/some.user/",
        "/reel/C8abc/liked_by/",
        "https://example.com/reel/C8abc/",
        "https://www.instagram.com.evil.com/reel/C8abc/",
    ],
)
def test_rejects_non_post_links(href):
    assert parse_post_url(href) is None


def test_post_url_is_canonical():
    assert post_url("C8abc") == "https://www.instagram.com/p/C8abc/"
    assert parse_post_url(post_url("C8abc")) == ("p", "C8abc")
