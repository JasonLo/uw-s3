"""Tests for rclone wrapper."""

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


def test_build_env_carries_credentials_inline() -> None:
    rm = _make_mount(
        access_key="testkey",
        secret_key="testsecret",
        endpoint="campus.s3.wisc.edu",
    )
    env = rm._build_env()
    assert env["RCLONE_CONFIG_UWS3_ACCESS_KEY_ID"] == "testkey"
    assert env["RCLONE_CONFIG_UWS3_SECRET_ACCESS_KEY"] == "testsecret"
    assert env["RCLONE_CONFIG_UWS3_ENDPOINT"] == "https://campus.s3.wisc.edu"
    assert env["RCLONE_CONFIG_UWS3_TYPE"] == "s3"
    assert env["RCLONE_CONFIG_UWS3_PROVIDER"] == "Other"


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
    rm._process.poll.return_value = None

    with pytest.raises(RuntimeError, match="already mounted"):
        rm.mount()


@patch("uw_s3.rclone.subprocess.Popen")
@patch("uw_s3.rclone.find_rclone", return_value="/usr/bin/rclone")
def test_mount_spawns_rclone(mock_find, mock_popen, tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_popen.return_value = mock_proc

    rm.mount()

    assert rm._process is mock_proc
    assert rm.is_mounted is True
    args = mock_popen.call_args[0][0]
    assert args[0] == "/usr/bin/rclone"
    assert "mount" in args
    assert "uws3:b" in args
    kwargs = mock_popen.call_args.kwargs
    assert kwargs["start_new_session"] is True
    assert "RCLONE_CONFIG_UWS3_ACCESS_KEY_ID" in kwargs["env"]


@patch("uw_s3.rclone.subprocess.Popen")
@patch("uw_s3.rclone.find_rclone", return_value="/usr/bin/rclone")
def test_mount_raises_with_stderr_when_rclone_exits_early(
    mock_find, mock_popen, tmp_path
) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 1
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read.return_value = b"bad endpoint\n"
    mock_popen.return_value = mock_proc

    with pytest.raises(RuntimeError, match="bad endpoint"):
        rm.mount()
    assert rm._process is None


@patch("uw_s3.rclone.os.killpg")
def test_unmount_terminates_process_group(mock_killpg) -> None:
    rm = _make_mount()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.pid = 1234
    mock_proc.wait.return_value = 0
    mock_proc.stderr = MagicMock()
    rm._process = mock_proc

    with patch("uw_s3.rclone.subprocess.run"):
        rm.unmount()

    mock_killpg.assert_called_once()
    assert rm._process is None


@patch("uw_s3.rclone.os.killpg")
def test_unmount_kills_on_timeout(mock_killpg) -> None:
    rm = _make_mount()
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    mock_proc.pid = 1234
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired("rclone", 5), 0]
    mock_proc.stderr = MagicMock()
    rm._process = mock_proc

    with patch("uw_s3.rclone.subprocess.run"):
        rm.unmount()

    # First call SIGTERMs the group, second call SIGKILLs after timeout.
    assert mock_killpg.call_count == 2


def test_unmount_noop_when_not_mounted() -> None:
    rm = _make_mount()
    with patch("uw_s3.rclone.subprocess.run"):
        rm.unmount()
