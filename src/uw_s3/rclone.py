"""Rclone wrapper for mounting S3 buckets as local folders via FUSE."""

import os
import shutil
import signal
import subprocess
import time
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
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def is_mounted(self) -> bool:
        """Check if the rclone subprocess is still running."""
        return self._process is not None and self._process.poll() is None

    def _build_env(self) -> dict[str, str]:
        """Return env with rclone S3 backend creds — no on-disk config file."""
        env = os.environ.copy()
        env["RCLONE_CONFIG_UWS3_TYPE"] = "s3"
        env["RCLONE_CONFIG_UWS3_PROVIDER"] = "Other"
        env["RCLONE_CONFIG_UWS3_ACCESS_KEY_ID"] = self.access_key
        env["RCLONE_CONFIG_UWS3_SECRET_ACCESS_KEY"] = self.secret_key
        env["RCLONE_CONFIG_UWS3_ENDPOINT"] = f"https://{self.endpoint}"
        return env

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

        # start_new_session puts rclone (and any FUSE helpers it spawns) in its
        # own process group so we can clean the whole tree up on unmount.
        self._process = subprocess.Popen(
            [
                rclone,
                "mount",
                "uws3:" + self.bucket,
                str(self.mount_point),
                "--vfs-cache-mode",
                "full",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=self._build_env(),
            start_new_session=True,
        )

        # rclone backgrounds itself once the mount is healthy. Wait briefly:
        # if it exits in this window, the mount failed and stderr has the reason.
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                err = b""
                if self._process.stderr is not None:
                    err = self._process.stderr.read() or b""
                self._process = None
                msg = err.decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    f"rclone exited before mount was ready: {msg or '(no stderr)'}"
                )
            time.sleep(0.05)

    def unmount(self) -> None:
        """Unmount the bucket and clean up subprocess + FUSE helpers."""
        proc = self._process
        if proc is not None and proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError, PermissionError:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError, PermissionError:
                    proc.kill()
                proc.wait(timeout=5)
        if proc is not None and proc.stderr is not None:
            proc.stderr.close()
        self._process = None

        # Belt-and-suspenders: if the kernel still has the mount, drop it.
        try:
            subprocess.run(
                ["fusermount", "-u", str(self.mount_point)],
                capture_output=True,
                timeout=5,
            )
        except FileNotFoundError, subprocess.TimeoutExpired:
            pass
