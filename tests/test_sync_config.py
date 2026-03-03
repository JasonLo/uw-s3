"""Tests for sync config persistence."""

from pathlib import Path

from uw_s3.sync.config import load_mappings, save_mappings, add_mapping, remove_mapping
from uw_s3.sync.models import SyncMap


def test_save_and_load_roundtrip(tmp_path: Path, monkeypatch: object) -> None:
    config_file = tmp_path / "sync.json"
    import uw_s3.sync.config as cfg

    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]

    mappings = [
        SyncMap(local_dir="/a", bucket="bucket-a"),
        SyncMap(local_dir="/b", bucket="bucket-b", prefix="data"),
    ]
    save_mappings(mappings)
    loaded = load_mappings()

    assert len(loaded) == 2
    assert loaded[0].local_dir == "/a"
    assert loaded[1].prefix == "data"


def test_load_empty_returns_empty_list(tmp_path: Path, monkeypatch: object) -> None:
    config_file = tmp_path / "sync.json"
    import uw_s3.sync.config as cfg

    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]

    assert load_mappings() == []


def test_add_mapping_appends(tmp_path: Path, monkeypatch: object) -> None:
    config_file = tmp_path / "sync.json"
    import uw_s3.sync.config as cfg

    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]

    m1 = SyncMap(local_dir="/a", bucket="b1")
    m2 = SyncMap(local_dir="/b", bucket="b2")
    add_mapping(m1)
    add_mapping(m2)

    loaded = load_mappings()
    assert len(loaded) == 2


def test_add_mapping_replaces_same_id(tmp_path: Path, monkeypatch: object) -> None:
    config_file = tmp_path / "sync.json"
    import uw_s3.sync.config as cfg

    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]

    m = SyncMap(local_dir="/a", bucket="b1")
    add_mapping(m)
    add_mapping(m)

    loaded = load_mappings()
    assert len(loaded) == 1


def test_remove_mapping(tmp_path: Path, monkeypatch: object) -> None:
    config_file = tmp_path / "sync.json"
    import uw_s3.sync.config as cfg

    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]

    m = SyncMap(local_dir="/a", bucket="b1")
    add_mapping(m)
    remove_mapping(m.id)

    assert load_mappings() == []


def test_load_corrupt_json_raises(tmp_path: Path, monkeypatch: object) -> None:
    config_file = tmp_path / "sync.json"
    import uw_s3.sync.config as cfg

    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)  # type: ignore[attr-defined]

    config_file.write_text("not valid json{{{")
    try:
        load_mappings()
        assert False, "Expected an exception"
    except Exception:
        pass
