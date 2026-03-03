"""Tests for rclone wrapper."""

import os
import stat
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from uw_s3.rclone import RcloneMount


def _make_mount(**overrides: object) -> RcloneMount:
    defaults: dict[str, object] = {
        "access_key": "k",
        "secret_key": "s",
        "endpoint": "campus.s3.wisc.edu",
        "bucket": "b",
        "mount_point": "/tmp/test",
    }
    defaults.update(overrides)
    return RcloneMount(**defaults)  # type: ignore[arg-type]


def test_write_config_permissions() -> None:
    rm = _make_mount(
        access_key="testkey",
        secret_key="testsecret",
        bucket="test-bucket",
        mount_point="/tmp/test-mount",
    )
    path = rm._write_config()
    try:
        mode = os.stat(path).st_mode
        assert not (mode & stat.S_IRGRP), "group should not have read"
        assert not (mode & stat.S_IROTH), "others should not have read"

        content = path.read_text()
        assert "testkey" in content
        assert "testsecret" in content
        assert "campus.s3.wisc.edu" in content
    finally:
        path.unlink()


def test_is_mounted_false_initially() -> None:
    rm = _make_mount()
    assert rm.is_mounted is False


def test_mount_raises_when_rclone_not_found(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    with patch("uw_s3.rclone.find_rclone", return_value=None):
        with pytest.raises(FileNotFoundError, match="rclone is not installed"):
            rm.mount()


def test_mount_raises_when_already_mounted(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    rm._process = MagicMock()
    rm._process.poll.return_value = None  # still running

    with pytest.raises(RuntimeError, match="already mounted"):
        rm.mount()


@patch("uw_s3.rclone.subprocess.Popen")
@patch("uw_s3.rclone.find_rclone", return_value="/usr/bin/rclone")
def test_mount_spawns_rclone(mock_find, mock_popen, tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # simulate running process
    mock_popen.return_value = mock_proc

    rm.mount()

    assert rm._process is mock_proc
    assert rm.is_mounted is True
    args = mock_popen.call_args[0][0]
    assert args[0] == "/usr/bin/rclone"
    assert "mount" in args
    assert rm._config_file is not None
    rm._cleanup_config()


def test_unmount_terminates_process() -> None:
    rm = _make_mount()
    mock_proc = MagicMock()
    mock_proc.wait.return_value = 0
    rm._process = mock_proc
    rm._config_file = None

    with patch("uw_s3.rclone.subprocess.run"):
        rm.unmount()

    mock_proc.terminate.assert_called_once()
    assert rm._process is None


def test_unmount_kills_on_timeout() -> None:
    rm = _make_mount()
    mock_proc = MagicMock()
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired("rclone", 5), 0]
    rm._process = mock_proc
    rm._config_file = None

    with patch("uw_s3.rclone.subprocess.run"):
        rm.unmount()

    mock_proc.terminate.assert_called_once()
    mock_proc.kill.assert_called_once()


def test_unmount_cleans_up_config(tmp_path) -> None:
    rm = _make_mount()
    config = tmp_path / "rclone.conf"
    config.write_text("[uw-s3]")
    rm._process = None
    rm._config_file = config

    with patch("uw_s3.rclone.subprocess.run"):
        rm.unmount()

    assert not config.exists()
    assert rm._config_file is None


def test_unmount_noop_when_not_mounted() -> None:
    rm = _make_mount()
    with patch("uw_s3.rclone.subprocess.run"):
        rm.unmount()  # should not raise
