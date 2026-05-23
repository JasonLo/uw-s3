"""In-process FUSE mount of an S3 bucket via fsspec + s3fs.

The FUSE handler runs in a daemon thread inside the calling Python
process. When the process dies the kernel reaps the mount on its own;
a brief ENOTCONN window can remain after a crash, which
`_clear_stale_mount` handles defensively on the next mount() call.
"""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import os
import subprocess
import threading
import time
from pathlib import Path


def find_backend() -> str | None:
    """Return a backend identifier if Python s3fs + fsspec.fuse are importable."""
    s3fs_spec = importlib.util.find_spec("s3fs")
    fuse_spec = importlib.util.find_spec("fsspec.fuse")
    if s3fs_spec is not None and fuse_spec is not None:
        return "python:s3fs"
    return None


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

    def _clear_stale_mount(self) -> bool:
        """Force-unmount mount_point if it's a dead FUSE endpoint from a prior crash."""
        try:
            os.listdir(self.mount_point)
            return False
        except OSError as exc:
            if exc.errno not in (errno.ENOTCONN, errno.ESTALE):
                return False
        for args in (
            ["fusermount", "-u", str(self.mount_point)],
            ["fusermount", "-uz", str(self.mount_point)],
        ):
            with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
                result = subprocess.run(args, capture_output=True, timeout=5)
                if result.returncode == 0:
                    return True
        return False

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

        self.cleared_stale = self._clear_stale_mount()
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

        # Thread alive but mount never appeared — tear down and surface.
        self._teardown_mountpoint()
        self._thread = None
        raise RuntimeError(
            f"Python s3fs did not establish a mount at {self.mount_point} within 10s"
        )

    def _teardown_mountpoint(self) -> None:
        for args in (
            ["fusermount", "-u", str(self.mount_point)],
            ["fusermount", "-uz", str(self.mount_point)],
        ):
            with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
                result = subprocess.run(args, capture_output=True, timeout=5)
                if result.returncode == 0:
                    break

    def unmount(self) -> None:
        """Unmount the bucket; the FUSE handler thread exits on its own."""
        self._teardown_mountpoint()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
