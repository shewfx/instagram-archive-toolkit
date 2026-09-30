import json
from pathlib import Path

import pytest

from src import config


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    for key in config.EDITABLE:  # undo whatever a test applies
        monkeypatch.setattr(config, key, getattr(config, key))
    return path


def test_save_applies_and_writes_settings(settings_file):
    config.save_settings({"ITEM_DELAY": "7.5", "BATCH_SIZE": 10, "LIKED_HTML": r"D:\x\liked.html"})
    assert config.ITEM_DELAY == 7.5 and config.BATCH_SIZE == 10
    assert config.LIKED_HTML == Path(r"D:\x\liked.html")
    stored = json.loads(settings_file.read_text(encoding="utf-8"))
    assert stored["ITEM_DELAY"] == 7.5 and stored["LIKED_HTML"] == r"D:\x\liked.html"
    assert set(stored) == set(config.EDITABLE)


@pytest.mark.parametrize(
    "values",
    [
        {"ITEM_DELAY": config.MIN_ITEM_DELAY - 0.1},  # never faster than the default
        {"ITEM_DELAY": "nan"},
        {"BATCH_SIZE": 0},
        {"DB_PATH": "  "},
        {"COOKIES": "x"},  # only the listed settings exist
    ],
)
def test_invalid_settings_change_nothing(settings_file, values):
    before = config.current_settings()
    with pytest.raises(ValueError):
        config.save_settings({"BATCH_SIZE": 50, **values})
    assert config.current_settings() == before
    assert not settings_file.exists()


def test_empty_export_path_means_not_configured(settings_file):
    config.apply_settings({"SAVED_HTML": ""})
    assert config.SAVED_HTML is None


def test_export_cutoff_can_be_set_with_any_offset(settings_file):
    from datetime import datetime, timedelta, timezone

    config.save_settings({"EXPORT_SINCE": "2025-01-01T00:00:00+02:00"})
    assert config.EXPORT_SINCE == datetime(2024, 12, 31, 22, 0, tzinfo=timezone.utc)
    assert config.EXPORT_SINCE.utcoffset() == timedelta(hours=2)
    stored = json.loads(settings_file.read_text(encoding="utf-8"))
    assert stored["EXPORT_SINCE"] == "2025-01-01T00:00:00+02:00"
    config.apply_settings({"EXPORT_SINCE": "2025-01-01T00:00:00Z"})
    assert config.EXPORT_SINCE == config.DEFAULT_EXPORT_SINCE


def test_export_cutoff_needs_a_time_zone(settings_file):
    with pytest.raises(ValueError, match="time zone"):
        config.apply_settings({"EXPORT_SINCE": "2025-01-01T00:00:00"})
