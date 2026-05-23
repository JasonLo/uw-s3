"""Rclone wrapper for mounting S3 buckets as local folders via FUSE."""

import os
import shutil
import signal
import subprocess
import tempfile
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
        self.log_path: Path | None = None

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

        log_fd, log_path = tempfile.mkstemp(
            prefix=f"uws3-rclone-{self.bucket}-", suffix=".log"
        )
        os.close(log_fd)
        self.log_path = Path(log_path)

        # start_new_session puts rclone (and any FUSE helpers it spawns) in its
        # own process group so we can clean the whole tree up on unmount.
        # stderr/stdout go to a log file so the pipe buffer can't fill and block
        # rclone (which previously left the mount alive but unresponsive).
        self._process = subprocess.Popen(
            [
                rclone,
                "mount",
                "uws3:" + self.bucket,
                str(self.mount_point),
                "--vfs-cache-mode",
                "full",
                "--log-file",
                str(self.log_path),
                "--log-level",
                "INFO",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=self._build_env(),
            start_new_session=True,
        )

        # rclone stays in the foreground; we poll for the mount to actually
        # come up. If the process dies, or it never mounts within the deadline,
        # the mount failed and the log file has the reason.
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self._raise_with_log("rclone exited before mount was ready")
            if os.path.ismount(self.mount_point):
                return
            time.sleep(0.1)

        # Process is alive but mount never appeared — tear down and surface log.
        self._terminate_process()
        self._raise_with_log("rclone did not establish a mount within 10s")

    def _terminate_process(self) -> None:
        proc = self._process
        if proc is None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                proc.kill()
        self._process = None

    def _raise_with_log(self, prefix: str) -> None:
        tail = ""
        if self.log_path is not None and self.log_path.exists():
            try:
                tail = self.log_path.read_text(errors="replace").strip().splitlines()[-10:]
                tail = "\n".join(tail)
            except OSError:
                tail = ""
        log_hint = f" (full log: {self.log_path})" if self.log_path else ""
        raise RuntimeError(f"{prefix}{log_hint}\n{tail}" if tail else f"{prefix}{log_hint}")

    def unmount(self) -> None:
        """Unmount the bucket and clean up subprocess + FUSE helpers."""
        self._terminate_process()

        # Belt-and-suspenders: if the kernel still has the mount, drop it.
        try:
            subprocess.run(
                ["fusermount", "-u", str(self.mount_point)],
                capture_output=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        if self.log_path is not None:
            try:
                self.log_path.unlink(missing_ok=True)
            except OSError:
                pass
            self.log_path = None
