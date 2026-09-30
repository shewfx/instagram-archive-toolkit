import json
import os

import pytest

from src import config, database, services
from tests.test_search import LIKED_HTML, SAVED_HTML


def test_build_index_then_load_and_describe(tmp_path):
    liked_html, saved_html = tmp_path / "liked.html", tmp_path / "saved.html"
    liked_html.write_text(LIKED_HTML, encoding="utf-8")
    saved_html.write_text(SAVED_HTML, encoding="utf-8")
    paths = {"liked": tmp_path / "liked.json", "saved": tmp_path / "saved.json"}

    assert len(services.build_index("liked", liked_html, paths["liked"])) == 3
    assert services.manifest_info(paths["saved"]) is None
    services.build_index("saved", saved_html, paths["saved"])

    info = services.manifest_info(paths["liked"])
    assert (info["entries"], info["reels"]) == (3, 2)
    records = services.load_posts(paths, ["liked", "saved"])
    assert {r["source"] for r in records} == {"liked", "saved"}
    assert len(services.load_posts(paths, ["saved"])) == 2


def test_load_posts_explains_a_missing_index(tmp_path):
    with pytest.raises(FileNotFoundError, match="build-search --saved"):
        services.load_posts({"saved": tmp_path / "none.json"}, ["saved"])


def test_rebuilt_index_is_reread(tmp_path):
    path = tmp_path / "liked.json"
    path.write_text(json.dumps([{"a": 1}]), encoding="utf-8")
    assert services.load_posts({"liked": path}, ["liked"]) == [{"a": 1}]
    path.write_text(json.dumps([{"a": 1}, {"a": 2}]), encoding="utf-8")
    os.utime(path, (1, 2))  # a different mtime, as a rebuild gives
    assert len(services.load_posts({"liked": path}, ["liked"])) == 2


def test_with_db_uses_the_configured_database(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "x.db")
    services.with_db(database.add_reel, "A", "u")
    assert services.with_db(database.status_counts)["pending"] == 1
