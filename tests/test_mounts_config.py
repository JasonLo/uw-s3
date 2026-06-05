"""Tests for the detached-mount persistence layer (I-3)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import uw_s3.mounts_config as cfg
from uw_s3.mounts_config import MountRecord


@pytest.fixture
def mounts_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_file = tmp_path / "mounts.json"
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)
    return config_file


def _record(bucket: str = "b", pid: int | None = None) -> MountRecord:
    return MountRecord(
        bucket=bucket,
        endpoint="campus.s3.wisc.edu",
        mount_point=f"/tmp/{bucket}",
        pid=pid if pid is not None else os.getpid(),
        started_at=1234.0,
    )


def test_load_empty_when_no_file(mounts_file: Path) -> None:
    assert cfg.load() == []


def test_save_load_roundtrip(mounts_file: Path) -> None:
    cfg.save([_record("a"), _record("b")])
    loaded = cfg.load()
    assert [r.bucket for r in loaded] == ["a", "b"]


def test_load_corrupt_json_returns_empty(mounts_file: Path) -> None:
    mounts_file.write_text("not json {{{")
    assert cfg.load() == []


def test_add_appends(mounts_file: Path) -> None:
    cfg.add(_record("a"))
    cfg.add(_record("b"))
    assert {r.bucket for r in cfg.load()} == {"a", "b"}


def test_add_replaces_same_bucket_and_path(mounts_file: Path) -> None:
    cfg.add(_record("a"))
    cfg.add(_record("a"))  # same bucket, same default mount_point
    loaded = cfg.load()
    assert len(loaded) == 1


def test_remove(mounts_file: Path) -> None:
    rec = _record("a")
    cfg.add(rec)
    cfg.remove(rec.bucket, rec.mount_point)
    assert cfg.load() == []


def test_is_record_live_true_for_self_and_mounted(mounts_file: Path) -> None:
    rec = _record("a")
    with patch("uw_s3.mounts_config.os.path.ismount", return_value=True):
        assert cfg.is_record_live(rec) is True


def test_is_record_live_false_when_pid_dead(mounts_file: Path) -> None:
    rec = _record("a", pid=999_999_99)  # very unlikely to exist
    assert cfg.is_record_live(rec) is False


def test_is_record_live_false_when_unmounted(mounts_file: Path) -> None:
    rec = _record("a")
    with patch("uw_s3.mounts_config.os.path.ismount", return_value=False):
        assert cfg.is_record_live(rec) is False


def test_clear_dead_drops_stale_returns_them(mounts_file: Path) -> None:
    alive = _record("alive", pid=os.getpid())
    dead = _record("dead", pid=999_999_99)
    cfg.save([alive, dead])

    with patch("uw_s3.mounts_config.os.path.ismount", return_value=True):
        dropped = cfg.clear_dead()

    assert [r.bucket for r in dropped] == ["dead"]
    assert [r.bucket for r in cfg.load()] == ["alive"]


def test_clear_dead_noop_when_all_alive(mounts_file: Path) -> None:
    cfg.save([_record("a"), _record("b")])
    with patch("uw_s3.mounts_config.os.path.ismount", return_value=True):
        dropped = cfg.clear_dead()
    assert dropped == []
    assert len(cfg.load()) == 2


def test_persisted_file_contains_no_credentials(mounts_file: Path) -> None:
    """Constitution §9: credentials MUST NEVER be persisted."""
    cfg.add(_record("a"))
    raw = mounts_file.read_text()
    parsed = json.loads(raw)
    forbidden_keys = {
        "access_key",
        "secret_key",
        "S3_ACCESS_KEY_ID",
        "S3_SECRET_ACCESS_KEY",
        "key",
        "secret",
    }
    for entry in parsed:
        assert forbidden_keys.isdisjoint(entry.keys()), (
            f"credential-like key leaked into mounts.json: {entry}"
        )
