"""In-process and detached FUSE mounts of an S3 bucket via fsspec + s3fs.

`Mount` runs the FUSE handler in a daemon thread inside the caller's process.
`WorkerMount` shells out to `python -m uw_s3.mount_worker`, which holds the
mount in a detached subprocess that outlives the TUI per Constitution §10.
"""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from uw_s3.mounts_config import MountRecord


def find_backend() -> str | None:
    """Return a backend identifier if Python s3fs + fsspec.fuse are importable."""
    s3fs_spec = importlib.util.find_spec("s3fs")
    fuse_spec = importlib.util.find_spec("fsspec.fuse")
    if s3fs_spec is not None and fuse_spec is not None:
        return "python:s3fs"
    return None


def clear_stale_mount(mount_point: str | Path) -> bool:
    """Force-unmount `mount_point` if it's a dead FUSE endpoint from a prior crash."""
    path = Path(mount_point).expanduser().resolve()
    try:
        os.listdir(path)
        return False
    except OSError as exc:
        if exc.errno not in (errno.ENOTCONN, errno.ESTALE):
            return False
    return teardown_mountpoint(path)


def teardown_mountpoint(mount_point: str | Path) -> bool:
    """Run `fusermount -u` (then `-uz`) on the mount point; return True on success."""
    path = str(Path(mount_point).expanduser())
    for args in (
        ["fusermount", "-u", path],
        ["fusermount", "-uz", path],
    ):
        with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
            result = subprocess.run(args, capture_output=True, timeout=5)
            if result.returncode == 0:
                return True
    return False


class Mount:
    """Manage an in-process FUSE mount of an S3 bucket via Python s3fs."""

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
        self._thread: threading.Thread | None = None
        self._fuse_error: BaseException | None = None
        self.cleared_stale: bool = False

    @property
    def is_mounted(self) -> bool:
        """Whether the FUSE handler thread is alive and the kernel sees a mount."""
        if self._thread is None or not self._thread.is_alive():
            return False
        return os.path.ismount(self.mount_point)

    def _run_fuse(self, fs: object) -> None:
        try:
            import fsspec.fuse

            fsspec.fuse.run(
                fs=fs,
                path=self.bucket,
                mount_point=str(self.mount_point),
                foreground=True,
            )
        except BaseException as exc:
            self._fuse_error = exc

    def mount(self) -> None:
        """Mount the bucket at the configured mount point."""
        if self.is_mounted:
            raise RuntimeError(
                f"{self.bucket} is already mounted at {self.mount_point}"
            )

        try:
            import s3fs
        except ImportError as exc:
            raise FileNotFoundError(
                "Python s3fs is not installed. Run `uv sync` to install it."
            ) from exc

        self.cleared_stale = clear_stale_mount(self.mount_point)
        self.mount_point.mkdir(parents=True, exist_ok=True)

        # use_listings_cache=False makes external writes visible on the very
        # next listing — see specs/2_INTENT/IT-2-s3fs-migration/experiments/results.md for the data.
        fs = s3fs.S3FileSystem(
            key=self.access_key,
            secret=self.secret_key,
            client_kwargs={"endpoint_url": f"https://{self.endpoint}"},
            use_listings_cache=False,
        )

        self._fuse_error = None
        self._thread = threading.Thread(
            target=self._run_fuse,
            args=(fs,),
            daemon=True,
            name=f"s3fs-mount-{self.bucket}",
        )
        self._thread.start()

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if not self._thread.is_alive():
                err = self._fuse_error
                msg = f"Python s3fs mount thread exited before {self.mount_point} was ready"
                if err is not None:
                    msg = f"{msg}\n{type(err).__name__}: {err}"
                self._thread = None
                raise RuntimeError(msg)
            if os.path.ismount(self.mount_point):
                return
            time.sleep(0.1)

        teardown_mountpoint(self.mount_point)
        self._thread = None
        raise RuntimeError(
            f"Python s3fs did not establish a mount at {self.mount_point} within 10s"
        )

    def unmount(self) -> None:
        """Unmount the bucket; the FUSE handler thread exits on its own."""
        teardown_mountpoint(self.mount_point)
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


class WorkerMount:
    """Manage a detached `uws3-mount-worker` subprocess holding a FUSE mount.

    The worker is launched with `start_new_session=True` so it survives the
    parent TUI's exit; it is signalled with SIGTERM to unmount. Credentials
    cross the process boundary only via the worker's environment (§9).
    """

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
        self.pid: int | None = None
        self.started_at: float | None = None
        self.cleared_stale: bool = False

    @classmethod
    def attach(cls, record: MountRecord) -> WorkerMount:
        """Build a proxy around an already-running worker described by `record`.

        Used at TUI restart. Credentials are NOT recovered (they never hit disk);
        the proxy can unmount and inspect status but cannot re-mount.
        """
        instance = cls(
            access_key="",
            secret_key="",
            endpoint=record.endpoint,
            bucket=record.bucket,
            mount_point=record.mount_point,
        )
        instance.pid = record.pid
        instance.started_at = record.started_at
        return instance

    @property
    def is_mounted(self) -> bool:
        """True when the worker PID is alive AND the mount point reports as mounted."""
        if self.pid is None:
            return False
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            pass
        return os.path.ismount(self.mount_point)

    def mount(self) -> None:
        """Spawn a detached worker and wait until the mount point is live."""
        if self.is_mounted:
            raise RuntimeError(
                f"{self.bucket} is already mounted at {self.mount_point}"
            )
        if not self.access_key or not self.secret_key:
            raise RuntimeError(
                "WorkerMount.mount() requires credentials; use attach() for restored mounts"
            )

        self.cleared_stale = clear_stale_mount(self.mount_point)
        self.mount_point.mkdir(parents=True, exist_ok=True)

        env = {
            **os.environ,
            "S3_ACCESS_KEY_ID": self.access_key,
            "S3_SECRET_ACCESS_KEY": self.secret_key,
        }
        argv = [
            sys.executable,
            "-m",
            "uw_s3.mount_worker",
            "--marker",
            "uws3-mount-worker",
            "--bucket",
            self.bucket,
            "--endpoint",
            self.endpoint,
            "--mount-point",
            str(self.mount_point),
        ]
        proc = subprocess.Popen(
            argv,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        self.pid = proc.pid
        self.started_at = time.time()

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            exit_code = proc.poll()
            if exit_code is not None:
                self.pid = None
                self.started_at = None
                raise RuntimeError(
                    f"uws3-mount-worker exited with code {exit_code} before "
                    f"{self.mount_point} was ready"
                )
            if os.path.ismount(self.mount_point):
                return
            time.sleep(0.1)

        self._signal_and_wait(signal.SIGTERM, 5.0)
        teardown_mountpoint(self.mount_point)
        self.pid = None
        self.started_at = None
        raise RuntimeError(
            f"uws3-mount-worker did not establish a mount at {self.mount_point} within 10s"
        )

    def unmount(self) -> None:
        """Signal the worker, wait briefly, fall back to fusermount if needed."""
        if self.pid is not None:
            self._signal_and_wait(signal.SIGTERM, 5.0)
        teardown_mountpoint(self.mount_point)
        self.pid = None
        self.started_at = None

    def _signal_and_wait(self, sig: int, timeout: float) -> None:
        """Send `sig` to the worker, poll until it dies or `timeout` elapses."""
        if self.pid is None:
            return
        try:
            os.kill(self.pid, sig)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                os.kill(self.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.1)

    def to_record(self) -> MountRecord:
        """Snapshot this mount as a persistable `MountRecord`."""
        if self.pid is None or self.started_at is None:
            raise RuntimeError("WorkerMount.to_record() called before mount()")
        return MountRecord(
            bucket=self.bucket,
            endpoint=self.endpoint,
            mount_point=str(self.mount_point),
            pid=self.pid,
            started_at=self.started_at,
        )
