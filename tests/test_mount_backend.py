"""Tests for the in-process Python s3fs mount backend."""

from __future__ import annotations

import errno
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from uw_s3.mount_backend import Mount, find_backend


def _make_mount(**overrides: object) -> Mount:
    defaults: dict[str, object] = {
        "access_key": "k",
        "secret_key": "s",
        "endpoint": "campus.s3.wisc.edu",
        "bucket": "b",
        "mount_point": "/tmp/test",
    }
    defaults.update(overrides)
    return Mount(**defaults)  # type: ignore[arg-type]


def _fake_s3fs_module() -> MagicMock:
    """Build a MagicMock that stands in for the s3fs module via sys.modules."""
    mod = MagicMock(name="s3fs")
    mod.S3FileSystem.return_value = MagicMock(name="S3FileSystem-instance")
    return mod


def test_find_backend_returns_identifier_when_deps_present() -> None:
    # s3fs and fsspec.fuse are project deps; both should be importable.
    assert find_backend() == "python:s3fs"


def test_find_backend_returns_none_when_s3fs_missing() -> None:
    with patch("uw_s3.mount_backend.importlib.util.find_spec", return_value=None):
        assert find_backend() is None


def test_is_mounted_false_initially(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    assert rm.is_mounted is False


def test_is_mounted_false_when_thread_is_none(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    rm._thread = None
    assert rm.is_mounted is False


def test_is_mounted_false_when_thread_dead(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    rm._thread = dead
    assert rm.is_mounted is False


def test_mount_raises_when_s3fs_not_importable(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    # Replacing the entry with None makes "import s3fs" raise ImportError.
    with patch.dict(sys.modules, {"s3fs": None}):
        with pytest.raises(FileNotFoundError, match="Python s3fs is not installed"):
            rm.mount()


def test_mount_raises_when_already_mounted(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    alive = MagicMock(spec=threading.Thread)
    alive.is_alive.return_value = True
    rm._thread = alive

    with patch("uw_s3.mount_backend.os.path.ismount", return_value=True):
        with pytest.raises(RuntimeError, match="already mounted"):
            rm.mount()


def test_mount_builds_s3filesystem_with_endpoint_and_no_listings_cache(
    tmp_path,
) -> None:
    rm = _make_mount(
        mount_point=str(tmp_path / "mnt"),
        endpoint="campus.s3.wisc.edu",
        access_key="ak",
        secret_key="sk",
    )
    fake_s3fs = _fake_s3fs_module()

    with patch.dict(sys.modules, {"s3fs": fake_s3fs}):
        with patch("uw_s3.mount_backend.os.path.ismount", side_effect=[False, True]):
            with patch.object(threading.Thread, "start", lambda self: None):
                with patch.object(threading.Thread, "is_alive", return_value=True):
                    rm.mount()

    fake_s3fs.S3FileSystem.assert_called_once()
    kwargs = fake_s3fs.S3FileSystem.call_args.kwargs
    assert kwargs["key"] == "ak"
    assert kwargs["secret"] == "sk"
    assert kwargs["client_kwargs"] == {"endpoint_url": "https://campus.s3.wisc.edu"}
    assert kwargs["use_listings_cache"] is False
    assert rm._thread is not None


def test_mount_raises_when_thread_dies_before_mount_ready(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    fake_s3fs = _fake_s3fs_module()

    def start_then_die(self):  # noqa: ANN001
        # Simulate the FUSE runner raising and being captured by _run_fuse.
        rm._fuse_error = RuntimeError("bad endpoint")

    with patch.dict(sys.modules, {"s3fs": fake_s3fs}):
        with patch("uw_s3.mount_backend.os.path.ismount", return_value=False):
            with patch.object(threading.Thread, "start", start_then_die):
                with patch.object(threading.Thread, "is_alive", return_value=False):
                    with pytest.raises(RuntimeError, match="bad endpoint"):
                        rm.mount()

    assert rm._thread is None


def test_mount_raises_on_timeout_and_tears_down_mountpoint(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    fake_s3fs = _fake_s3fs_module()

    # Force the deadline-poll to exit via the timeout branch by giving
    # monotonic() values that exceed the 10s budget on the second sample.
    monotonic_values = iter([0.0, 0.0, 11.0])

    with patch.dict(sys.modules, {"s3fs": fake_s3fs}):
        with patch(
            "uw_s3.mount_backend.os.path.ismount", return_value=False
        ):  # never ready
            with patch(
                "uw_s3.mount_backend.time.monotonic",
                side_effect=lambda: next(monotonic_values),
            ):
                with patch("uw_s3.mount_backend.time.sleep"):
                    with patch("uw_s3.mount_backend.subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(returncode=0)
                        with patch.object(threading.Thread, "start", lambda self: None):
                            with patch.object(
                                threading.Thread, "is_alive", return_value=True
                            ):
                                with pytest.raises(
                                    RuntimeError, match="did not establish a mount"
                                ):
                                    rm.mount()

    assert rm._thread is None
    # _teardown_mountpoint tried fusermount -u as the cleanup
    cmds = [call.args[0] for call in mock_run.call_args_list]
    assert any(c[:2] == ["fusermount", "-u"] for c in cmds)


def test_unmount_runs_fusermount_and_joins_thread(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    mock_thread = MagicMock(spec=threading.Thread)
    rm._thread = mock_thread

    with patch("uw_s3.mount_backend.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        rm.unmount()

    first_call_args = mock_run.call_args_list[0].args[0]
    assert first_call_args[0] == "fusermount"
    assert first_call_args[1] == "-u"
    mock_thread.join.assert_called_once_with(timeout=5)
    assert rm._thread is None


def test_unmount_noop_when_thread_is_none(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    rm._thread = None
    with patch("uw_s3.mount_backend.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        rm.unmount()
    # fusermount still attempted as a belt-and-suspenders; no thread to join.
    assert mock_run.called


def test_clear_stale_mount_runs_fusermount_on_enotconn(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))

    def listdir_raises(_path):  # noqa: ANN001
        raise OSError(errno.ENOTCONN, "Transport endpoint is not connected")

    with patch("uw_s3.mount_backend.os.listdir", side_effect=listdir_raises):
        with patch("uw_s3.mount_backend.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert rm._clear_stale_mount() is True
            first_call_args = mock_run.call_args_list[0].args[0]
            assert first_call_args == ["fusermount", "-u", str(rm.mount_point)]


def test_clear_stale_mount_skips_on_healthy_dir(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    rm.mount_point.mkdir(parents=True, exist_ok=True)
    with patch("uw_s3.mount_backend.subprocess.run") as mock_run:
        assert rm._clear_stale_mount() is False
        mock_run.assert_not_called()


def test_clear_stale_mount_skips_on_unrelated_oserror(tmp_path) -> None:
    rm = _make_mount(mount_point=str(tmp_path / "mnt"))
    with patch(
        "uw_s3.mount_backend.os.listdir",
        side_effect=PermissionError("no permission"),
    ):
        with patch("uw_s3.mount_backend.subprocess.run") as mock_run:
            assert rm._clear_stale_mount() is False
            mock_run.assert_not_called()
