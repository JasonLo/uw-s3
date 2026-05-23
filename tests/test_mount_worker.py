"""Tests for the detached mount worker CLI (IT-3 / Constitution §10)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from uw_s3 import mount_worker


def _argv() -> list[str]:
    return [
        "--bucket",
        "b",
        "--endpoint",
        "campus.s3.wisc.edu",
        "--mount-point",
        "/tmp/m",
    ]


def test_parser_requires_bucket_endpoint_mountpoint() -> None:
    parser = mount_worker._build_parser()
    args = parser.parse_args(_argv())
    assert args.bucket == "b"
    assert args.endpoint == "campus.s3.wisc.edu"
    assert args.mount_point == "/tmp/m"
    assert args.marker == "uws3-mount-worker"


def test_parser_rejects_missing_required(capsys: pytest.CaptureFixture[str]) -> None:
    parser = mount_worker._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--bucket", "b"])


def test_main_returns_2_when_credentials_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("S3_SECRET_ACCESS_KEY", raising=False)
    assert mount_worker.main(_argv()) == 2


def test_main_returns_1_when_mount_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "s")
    fake_mount = MagicMock()
    fake_mount.mount.side_effect = RuntimeError("bad endpoint")
    with patch("uw_s3.mount_worker.Mount", return_value=fake_mount):
        assert mount_worker.main(_argv()) == 1


def test_main_blocks_until_signal_then_unmounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "s")
    fake_mount = MagicMock()

    class FakeEvent:
        def __init__(self) -> None:
            self._is_set = False

        def set(self) -> None:
            self._is_set = True

        def wait(self) -> None:
            # Pretend a signal already fired.
            self._is_set = True

    with patch("uw_s3.mount_worker.Mount", return_value=fake_mount):
        with patch("uw_s3.mount_worker.threading.Event", FakeEvent):
            rc = mount_worker.main(_argv())

    assert rc == 0
    fake_mount.mount.assert_called_once()
    fake_mount.unmount.assert_called_once()
