"""Tests for rclone wrapper."""

import os
import stat

from uw_s3.rclone import RcloneMount


def test_write_config_permissions() -> None:
    rm = RcloneMount(
        access_key="testkey",
        secret_key="testsecret",
        endpoint="campus.s3.wisc.edu",
        bucket="test-bucket",
        mount_point="/tmp/test-mount",
    )
    path = rm._write_config()
    try:
        mode = os.stat(path).st_mode
        # mkstemp creates with 0o600 — only owner should have access
        assert not (mode & stat.S_IRGRP), "group should not have read"
        assert not (mode & stat.S_IROTH), "others should not have read"

        content = path.read_text()
        assert "testkey" in content
        assert "testsecret" in content
        assert "campus.s3.wisc.edu" in content
    finally:
        path.unlink()


def test_is_mounted_false_initially() -> None:
    rm = RcloneMount(
        access_key="k",
        secret_key="s",
        endpoint="campus.s3.wisc.edu",
        bucket="b",
        mount_point="/tmp/test",
    )
    assert rm.is_mounted is False
