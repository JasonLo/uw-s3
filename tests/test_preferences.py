"""Tests for preferences module."""

from unittest.mock import patch

from uw_s3 import preferences


def test_load_preferences_missing_returns_empty(tmp_path) -> None:
    with patch.object(preferences, "PREFS_FILE", tmp_path / "missing.json"):
        assert preferences.load_preferences() == {}


def test_load_preferences_corrupt_json_returns_empty(tmp_path) -> None:
    f = tmp_path / "prefs.json"
    f.write_text("{not json")
    with patch.object(preferences, "PREFS_FILE", f):
        assert preferences.load_preferences() == {}


def test_save_then_load_roundtrip(tmp_path) -> None:
    f = tmp_path / "prefs.json"
    with (
        patch.object(preferences, "PREFS_FILE", f),
        patch.object(preferences, "CONFIG_DIR", tmp_path),
    ):
        preferences.save_preferences({"endpoint": "campus.s3.wisc.edu"})
        assert preferences.load_preferences() == {"endpoint": "campus.s3.wisc.edu"}


def test_update_preference_merges(tmp_path) -> None:
    f = tmp_path / "prefs.json"
    with (
        patch.object(preferences, "PREFS_FILE", f),
        patch.object(preferences, "CONFIG_DIR", tmp_path),
    ):
        preferences.save_preferences({"endpoint": "campus.s3.wisc.edu"})
        preferences.update_preference("last_bucket", "matryoshka")
        assert preferences.load_preferences() == {
            "endpoint": "campus.s3.wisc.edu",
            "last_bucket": "matryoshka",
        }
