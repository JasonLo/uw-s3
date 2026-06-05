"""Tests for the UWS3App survival/cleanup flow (I-3)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import uw_s3.mounts_config as cfg
from uw_s3.mount_backend import Mount, WorkerMount
from uw_s3.mounts_config import MountRecord
from uw_s3.tui.app import UWS3App


@pytest.fixture
def isolated_mounts_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect mounts.json into a tmp_path so tests can't smear the real one."""
    config_file = tmp_path / "mounts.json"
    monkeypatch.setattr(cfg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)
    return config_file


def _make_app() -> UWS3App:
    with patch("uw_s3.tui.app.load_preferences", return_value={}):
        return UWS3App(access_key="k", secret_key="s")


def test_unmount_all_calls_unmount_and_clears_dict(isolated_mounts_file: Path) -> None:
    app = _make_app()
    m1 = MagicMock(spec=Mount)
    m2 = MagicMock(spec=WorkerMount)
    m2.mount_point = "/tmp/m2"
    app.active_mounts = {"a": m1, "b": m2}

    # Pre-seed mounts.json for the WorkerMount entry.
    cfg.add(
        MountRecord(
            bucket="b",
            endpoint="campus.s3.wisc.edu",
            mount_point="/tmp/m2",
            pid=4242,
            started_at=1.0,
        )
    )

    app._unmount_all()

    m1.unmount.assert_called_once()
    m2.unmount.assert_called_once()
    assert app.active_mounts == {}
    assert cfg.load() == []


def test_detach_all_swaps_inprocess_to_worker_and_persists(
    isolated_mounts_file: Path,
) -> None:
    app = _make_app()
    in_proc = MagicMock(spec=Mount)
    in_proc.access_key = "k"
    in_proc.secret_key = "s"
    in_proc.endpoint = "campus.s3.wisc.edu"
    in_proc.bucket = "alpha"
    in_proc.mount_point = "/tmp/alpha"
    app.active_mounts = {"alpha": in_proc}

    def fake_mount(self: WorkerMount) -> None:
        self.pid = 9999
        self.started_at = 10.0

    with patch.object(WorkerMount, "mount", fake_mount):
        app._detach_all()

    in_proc.unmount.assert_called_once()
    persisted = cfg.load()
    assert len(persisted) == 1 and persisted[0].bucket == "alpha"
    assert isinstance(app.active_mounts["alpha"], WorkerMount)
    assert app.active_mounts["alpha"].bucket == "alpha"


def test_detach_all_leaves_existing_workers_alone(
    isolated_mounts_file: Path,
) -> None:
    app = _make_app()
    already_worker = WorkerMount.attach(
        MountRecord(
            bucket="beta",
            endpoint="campus.s3.wisc.edu",
            mount_point="/tmp/beta",
            pid=4242,
            started_at=1.0,
        )
    )
    app.active_mounts = {"beta": already_worker}

    with patch.object(WorkerMount, "mount") as mount:
        with patch.object(WorkerMount, "unmount") as unmount:
            app._detach_all()

    mount.assert_not_called()
    unmount.assert_not_called()


def test_restore_active_mounts_attaches_live_records_and_purges_dead(
    isolated_mounts_file: Path,
) -> None:
    app = _make_app()
    # Two records, one alive (current PID), one dead (large unused PID).
    import os

    cfg.save(
        [
            MountRecord(
                bucket="live",
                endpoint="campus.s3.wisc.edu",
                mount_point="/tmp/live",
                pid=os.getpid(),
                started_at=1.0,
            ),
            MountRecord(
                bucket="dead",
                endpoint="campus.s3.wisc.edu",
                mount_point="/tmp/dead",
                pid=999_999_99,
                started_at=2.0,
            ),
        ]
    )

    with patch("uw_s3.tui.app.clear_stale_mount") as clear_stale:
        with patch("uw_s3.mounts_config.os.path.ismount", return_value=True):
            app.restore_active_mounts()

    clear_stale.assert_called_once_with("/tmp/dead")
    assert list(app.active_mounts.keys()) == ["live"]
    assert isinstance(app.active_mounts["live"], WorkerMount)
    assert [r.bucket for r in cfg.load()] == ["live"]
