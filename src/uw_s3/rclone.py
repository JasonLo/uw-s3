"""Rclone wrapper for mounting S3 buckets as local folders via FUSE."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def find_rclone() -> str | None:
    """Return the path to rclone if installed, else None."""
    return shutil.which("rclone")


class RcloneMount:
    """Manage an rclone mount of an S3 bucket."""

    def __init__(
        self,
        *,
        access_key: str,
        secret_key: str,
        endpoint: str,
        bucket: str,
        mount_point: str | Path,
    ) -> None:
        self.access_key = access_key
        self.secret_key = secret_key
        self.endpoint = endpoint
        self.bucket = bucket
        self.mount_point = Path(mount_point).expanduser().resolve()
        self._process: subprocess.Popen[str] | None = None
        self._config_file: Path | None = None

    def _write_config(self) -> Path:
        """Write a temporary rclone config and return its path."""
        content = (
            "[uw-s3]\n"
            "type = s3\n"
            "provider = Other\n"
            f"access_key_id = {self.access_key}\n"
            f"secret_access_key = {self.secret_key}\n"
            f"endpoint = https://{self.endpoint}\n"
        )
        import os

        fd, path = tempfile.mkstemp(prefix="uw-s3-rclone-", suffix=".conf")
        try:
            os.write(fd, content.encode())
        finally:
            os.close(fd)
        return Path(path)

    @property
    def is_mounted(self) -> bool:
        """Check if the rclone subprocess is still running."""
        return self._process is not None and self._process.poll() is None

    def mount(self) -> None:
        """Mount the bucket at the configured mount point."""
        if self.is_mounted:
            raise RuntimeError(
                f"{self.bucket} is already mounted at {self.mount_point}"
            )

        rclone = find_rclone()
        if rclone is None:
            raise FileNotFoundError(
                "rclone is not installed. Install it from https://rclone.org/install/"
            )

        self.mount_point.mkdir(parents=True, exist_ok=True)
        self._config_file = self._write_config()

        self._process = subprocess.Popen(
            [
                rclone,
                "mount",
                f"uw-s3:{self.bucket}",
                str(self.mount_point),
                "--config",
                str(self._config_file),
                "--vfs-cache-mode",
                "full",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def unmount(self) -> None:
        """Unmount the bucket and clean up."""
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
            self._process = None

        # Fallback: fusermount -u in case the mount is still active
        _fusermount_errors = (FileNotFoundError, subprocess.TimeoutExpired)
        try:
            subprocess.run(
                ["fusermount", "-u", str(self.mount_point)],
                capture_output=True,
                timeout=5,
            )
        except _fusermount_errors:
            pass

        self._cleanup_config()

    def _cleanup_config(self) -> None:
        """Remove the temporary config file."""
        if self._config_file is not None:
            self._config_file.unlink(missing_ok=True)
            self._config_file = None

    def read_output(self) -> str:
        """Read any available stdout/stderr from rclone (non-blocking)."""
        if self._process is None or self._process.stdout is None:
            return ""
        import select

        # select.select works with pipes on Unix only
        if select.select([self._process.stdout], [], [], 0)[0]:
            return self._process.stdout.readline()
        return ""
