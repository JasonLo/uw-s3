"""Tests for the WorkerMount detached-subprocess wrapper (I-3)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from uw_s3.mount_backend import WorkerMount
from uw_s3.mounts_config import MountRecord


def _make_worker(**overrides: object) -> WorkerMount:
    defaults: dict[str, object] = {
        "access_key": "k",
        "secret_key": "s",
        "endpoint": "campus.s3.wisc.edu",
        "bucket": "b",
        "mount_point": "/tmp/test-worker",
    }
    defaults.update(overrides)
    return WorkerMount(**defaults)  # type: ignore[arg-type]


def test_attach_builds_proxy_without_credentials() -> None:
    record = MountRecord(
        bucket="b",
        endpoint="campus.s3.wisc.edu",
        mount_point="/tmp/m",
        pid=4242,
        started_at=99.0,
    )
    wm = WorkerMount.attach(record)
    assert wm.pid == 4242
    assert wm.bucket == "b"
    assert wm.access_key == ""
    assert wm.secret_key == ""


def test_is_mounted_false_when_pid_is_none(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"))
    assert wm.is_mounted is False


def test_is_mounted_false_when_pid_dead(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"))
    wm.pid = 999_999_99
    assert wm.is_mounted is False


def test_is_mounted_true_when_pid_alive_and_path_is_mount(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"))
    wm.pid = os.getpid()
    with patch("uw_s3.mount_backend.os.path.ismount", return_value=True):
        assert wm.is_mounted is True


def test_mount_raises_when_already_mounted(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"))
    wm.pid = os.getpid()
    with patch("uw_s3.mount_backend.os.path.ismount", return_value=True):
        with pytest.raises(RuntimeError, match="already mounted"):
            wm.mount()


def test_mount_refuses_when_no_credentials(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"), access_key="", secret_key="")
    with pytest.raises(RuntimeError, match="requires credentials"):
        wm.mount()


def test_mount_spawns_subprocess_with_marker_and_creds_in_env(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"))
    fake_proc = MagicMock(pid=12345)
    fake_proc.poll.return_value = None

    with patch("uw_s3.mount_backend.subprocess.Popen", return_value=fake_proc) as popen:
        with patch("uw_s3.mount_backend.os.path.ismount", side_effect=[False, True]):
            with patch("uw_s3.mount_backend.clear_stale_mount", return_value=False):
                wm.mount()

    popen.assert_called_once()
    call = popen.call_args
    argv = call.args[0]
    assert "uws3-mount-worker" in argv  # the --marker value
    assert "--bucket" in argv and "b" in argv
    env = call.kwargs["env"]
    assert env["S3_ACCESS_KEY_ID"] == "k"
    assert env["S3_SECRET_ACCESS_KEY"] == "s"
    assert call.kwargs["start_new_session"] is True
    assert wm.pid == 12345


def test_mount_raises_when_subprocess_exits_early(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"))
    fake_proc = MagicMock(pid=12345)
    fake_proc.poll.return_value = 2  # exited with code 2

    with patch("uw_s3.mount_backend.subprocess.Popen", return_value=fake_proc):
        with patch("uw_s3.mount_backend.os.path.ismount", return_value=False):
            with patch("uw_s3.mount_backend.clear_stale_mount", return_value=False):
                with pytest.raises(RuntimeError, match="exited with code 2"):
                    wm.mount()

    assert wm.pid is None


def test_unmount_signals_pid_and_runs_teardown(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"))
    wm.pid = os.getpid()  # use self so signal calls are safe via patching

    with patch("uw_s3.mount_backend.os.kill") as kill:
        with patch("uw_s3.mount_backend.subprocess.run") as run:
            run.return_value = MagicMock(returncode=0)
            kill.side_effect = [None, ProcessLookupError()]  # first SIGTERM, then dead
            wm.unmount()

    kill.assert_any_call(os.getpid(), 15)  # SIGTERM
    assert wm.pid is None


def test_to_record_raises_before_mount(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"))
    with pytest.raises(RuntimeError, match="called before mount"):
        wm.to_record()


def test_to_record_after_mount_carries_no_credentials(tmp_path) -> None:
    wm = _make_worker(mount_point=str(tmp_path / "m"))
    wm.pid = 12345
    wm.started_at = 99.0
    record = wm.to_record()
    # MountRecord schema is bucket/endpoint/mount_point/pid/started_at — no creds.
    assert set(vars(record).keys()) == {
        "bucket",
        "endpoint",
        "mount_point",
        "pid",
        "started_at",
    }
