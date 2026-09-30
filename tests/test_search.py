import json

from src import cli
from src.instagram.export import _ENTRY, parse_posts, search_posts, snippet


def row(label, value):
    return f'<tr><td class="_a6_q">{label}</td><td class="_2piu _a6_r">{value}</td></tr>'


def block(title, inner):
    return f'<h2 class="_3-95 _2pim _a6-h _a6-i">{title}</h2><div class="_a6-p">{inner}</div>'


def post(url, when, caption="", tags=(), name=None, username=None, partner=None, captions=1):
    # Mirrors the real export: URL, Caption row(s), Hashtags, Owner, optional Brand partner, date.
    tag_divs = "".join(
        f'<div><div class="x"><div class="_a6-p">{t}</div></div></div>' for t in tags
    )
    owner = (
        (row("URL", "https://example.com/") if name else "")
        + (row("Name", name) if name else "")
        + row("Username", username or "")
    )
    return (
        f'<div class="pam _3-95 _2ph- _a6-g {_ENTRY}<table>'
        f'<tr><td colspan="2" class="_a6_q">URL<div><a target="_blank" href="{url}">{url}</a>'
        "</div></td></tr>"
        + row("Caption", caption) * captions
        + (
            block("Hashtags", f'<div><div class="_2ph_ _a6_q">Name</div>{tag_divs}</div>')
            if tags
            else ""
        )
        + block("Owner", f'<div class="_a6-p"><table>{owner}</table></div>')
        + (
            block(
                "Brand partner", f"<table>{row('Name', 'Brand')}{row('Username', partner)}</table>"
            )
            if partner
            else ""
        )
        + f'</table></div><div class="_3-94 _a6-o">{when}</div></div>'
    )


LIKED_HTML = "".join(
    [
        post(
            "https://www.instagram.com/reel/HP1/",
            "Sep 28, 2026 2:46 am",
            "Harry\nPotter edit &amp; more 🧙‍♂️ #Hogwarts",
            tags=["hogwarts"],
            name="Wizard Fan",
            username="wizard.fan",
            captions=2,
        ),
        post(
            "https://www.instagram.com/p/GYM/",
            "Sep 27, 2026 1:00 pm",
            "Leg day",
            tags=["gymmotivation"],
            username="lifter",
            partner="protein.co",
        ),
        post(
            "https://www.instagram.com/reel/JP1/",
            "Sep 26, 2026 1:00 pm",
            "今夜、Vは会場に姿を現し",
            username="jp",
        ),
        post("https://www.instagram.com/reel/HP1/", "Jan 1, 2025 1:00 pm", "Harry Potter old like"),
    ]
)
SAVED_HTML = "".join(
    [
        post(
            "https://www.instagram.com/p/RE1/",
            "Sep 27, 2026 11:34 pm",
            "Claire and Jill, Resident Evil icons",
            name="Résident Évil Fans",
            username="re.fans",
        ),
        post("https://www.instagram.com/reel/HP2/", "Sep 28, 2026 5:00 am", "harry potter saved"),
    ]
)


def urls(records):
    return [r["url"] for r in records]


def test_parse_keeps_all_metadata_decoded_once_per_post():
    records = parse_posts(LIKED_HTML, "liked")
    assert urls(records) == [
        "https://www.instagram.com/reel/HP1/",
        "https://www.instagram.com/p/GYM/",
        "https://www.instagram.com/reel/JP1/",
    ]
    assert records[0] == {
        "source": "liked",
        "url": "https://www.instagram.com/reel/HP1/",
        "shortcode": "HP1",
        "post_type": "reel",
        "caption": "Harry\nPotter edit & more 🧙‍♂️ #Hogwarts",
        "hashtags": ["hogwarts"],
        "owner_name": "Wizard Fan",
        "username": "wizard.fan",
        "timestamp": "2026-09-28T09:46:00+00:00",
    }
    # Owner, not the Brand partner; no Name row means no owner_name.
    assert (records[1]["post_type"], records[1]["username"], records[1]["owner_name"]) == (
        "post",
        "lifter",
        None,
    )


def liked():
    return parse_posts(LIKED_HTML, "liked")


def saved():
    return parse_posts(SAVED_HTML, "saved")


def test_phrase_matches_case_insensitively_across_line_breaks():
    assert urls(search_posts(liked(), "harry potter")) == ["https://www.instagram.com/reel/HP1/"]
    assert urls(search_posts(liked(), "HARRY   POTTER")) == ["https://www.instagram.com/reel/HP1/"]
    assert search_posts(liked(), "potter harry") == []


def test_matches_caption_hashtag_username_and_owner_name():
    assert urls(search_posts(liked(), "leg day")) == ["https://www.instagram.com/p/GYM/"]
    assert urls(search_posts(liked(), "#gymmotivation")) == ["https://www.instagram.com/p/GYM/"]
    assert urls(search_posts(liked(), "wizard.fan")) == ["https://www.instagram.com/reel/HP1/"]
    assert urls(search_posts(liked(), "@lifter")) == ["https://www.instagram.com/p/GYM/"]
    assert urls(search_posts(saved(), "évil fans")) == ["https://www.instagram.com/p/RE1/"]
    # Brand partners are not the owner.
    assert search_posts(liked(), "protein.co") == []


def test_unicode_and_entities():
    assert urls(search_posts(liked(), "姿を現し")) == ["https://www.instagram.com/reel/JP1/"]
    assert urls(search_posts(liked(), "edit & more 🧙")) == ["https://www.instagram.com/reel/HP1/"]


def test_no_results_and_blank_query():
    assert search_posts(liked(), "resident evil") == []
    assert search_posts(liked(), "   ") == []


def test_snippet_centres_on_the_match():
    text = "a " * 100 + "Harry\nPotter" + " b" * 100
    s = snippet(text, "harry potter", width=4)
    assert s == "...a a Harry Potter b b..."
    assert snippet("short caption", "owner-only match") == "short caption"


def run(tmp_path, monkeypatch, capsys, sources, query):
    paths = {"liked": tmp_path / "liked.json", "saved": tmp_path / "saved.json"}
    paths["liked"].write_text(json.dumps(liked()), encoding="utf-8")
    paths["saved"].write_text(json.dumps(saved()), encoding="utf-8")
    monkeypatch.setattr(cli, "SEARCH_MANIFESTS", paths)
    hits = cli.search(sources, query)
    return hits, capsys.readouterr().out


def test_search_liked_and_saved_commands(tmp_path, monkeypatch, capsys):
    hits, out = run(tmp_path, monkeypatch, capsys, ["liked"], "harry potter")
    assert [(r["source"], r["url"]) for r in hits] == [
        ("liked", "https://www.instagram.com/reel/HP1/")
    ]
    assert "[LIKED]" in out and "@wizard.fan (Wizard Fan)" in out and "1 result for" in out

    hits, out = run(tmp_path, monkeypatch, capsys, ["saved"], "Resident Evil")
    assert urls(hits) == ["https://www.instagram.com/p/RE1/"]
    assert "[SAVED]" in out


def test_search_all_merges_newest_first_with_reels_and_posts(tmp_path, monkeypatch, capsys):
    hits, out = run(tmp_path, monkeypatch, capsys, ["liked", "saved"], "harry potter")
    assert [(r["source"], r["url"]) for r in hits] == [
        ("saved", "https://www.instagram.com/reel/HP2/"),  # Sep 28 12:00 UTC
        ("liked", "https://www.instagram.com/reel/HP1/"),  # Sep 28 09:46 UTC
    ]
    assert "2 results for 'harry potter'" in out

    hits, _ = run(tmp_path, monkeypatch, capsys, ["liked", "saved"], "e")
    assert {r["post_type"] for r in hits} == {"reel", "post"}


def test_search_all_no_results(tmp_path, monkeypatch, capsys):
    hits, out = run(tmp_path, monkeypatch, capsys, ["liked", "saved"], "zzz nothing")
    assert hits == []
    assert "0 results for 'zzz nothing'" in out
