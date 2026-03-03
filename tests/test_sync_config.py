"""Tests for sync config persistence."""

import json
from pathlib import Path

import pytest

import uw_s3.sync.config as cfg
from uw_s3.sync.config import load_mappings, save_mappings, add_mapping, remove_mapping
from uw_s3.sync.models import SyncMap


@pytest.fixture
def sync_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_file = tmp_path / "sync.json"
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)
    return config_file


def test_save_and_load_roundtrip(sync_config: Path) -> None:
    mappings = [
        SyncMap(local_dir="/a", bucket="bucket-a"),
        SyncMap(local_dir="/b", bucket="bucket-b", prefix="data"),
    ]
    save_mappings(mappings)
    loaded = load_mappings()

    assert len(loaded) == 2
    assert loaded[0].local_dir == "/a"
    assert loaded[1].prefix == "data"


def test_load_empty_returns_empty_list(sync_config: Path) -> None:
    assert load_mappings() == []


def test_add_mapping_appends(sync_config: Path) -> None:
    m1 = SyncMap(local_dir="/a", bucket="b1")
    m2 = SyncMap(local_dir="/b", bucket="b2")
    add_mapping(m1)
    add_mapping(m2)

    loaded = load_mappings()
    assert len(loaded) == 2


def test_add_mapping_replaces_same_id(sync_config: Path) -> None:
    m = SyncMap(local_dir="/a", bucket="b1")
    add_mapping(m)
    add_mapping(m)

    loaded = load_mappings()
    assert len(loaded) == 1


def test_remove_mapping(sync_config: Path) -> None:
    m = SyncMap(local_dir="/a", bucket="b1")
    add_mapping(m)
    remove_mapping(m.id)

    assert load_mappings() == []


def test_load_corrupt_json_raises(sync_config: Path) -> None:
    sync_config.write_text("not valid json{{{")
    with pytest.raises(json.JSONDecodeError):
        load_mappings()
