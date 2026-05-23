"""Evaluate Python s3fs + fsspec.fuse against a uw-s3 bucket.

Usage:
    uv run python experiments/s3fs_eval/try_s3fs_python.py <bucket> [campus|web]

Credentials are read from S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY (never
written to disk). Mount stays up; Ctrl-C unmounts.

Requires extra deps not in pyproject.toml during evaluation:
    uv pip install s3fs 'fsspec[fuse]' fusepy
"""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ENDPOINTS: dict[str, str] = {
    "campus": "campus.s3.wisc.edu",
    "web": "web.s3.wisc.edu",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bucket")
    parser.add_argument(
        "endpoint_key",
        nargs="?",
        default="campus",
        choices=list(ENDPOINTS),
    )
    args = parser.parse_args()

    access = os.environ.get("S3_ACCESS_KEY_ID")
    secret = os.environ.get("S3_SECRET_ACCESS_KEY")
    if not access or not secret:
        print("set S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY", file=sys.stderr)
        return 2

    endpoint = ENDPOINTS[args.endpoint_key]

    try:
        import fsspec.fuse
        import s3fs
    except ImportError as exc:
        print(
            f"missing deps: {exc}. "
            "install with: uv pip install s3fs 'fsspec[fuse]' fusepy",
            file=sys.stderr,
        )
        return 2

    fs = s3fs.S3FileSystem(
        key=access,
        secret=secret,
        client_kwargs={"endpoint_url": f"https://{endpoint}"},
        use_listings_cache=False,
    )

    mnt = Path(tempfile.mkdtemp(prefix="s3fs-py-eval-"))
    print(f"mount point: {mnt}")
    print(f"endpoint:    https://{endpoint}")
    print(f"bucket:      {args.bucket}")
    print()

    t0 = time.monotonic()
    fuse_thread = threading.Thread(
        target=fsspec.fuse.run,
        kwargs={
            "fs": fs,
            "path": args.bucket,
            "mount_point": str(mnt),
            "foreground": True,
        },
        daemon=True,
    )
    fuse_thread.start()

    deadline = t0 + 10.0
    while time.monotonic() < deadline:
        if os.path.ismount(mnt):
            break
        time.sleep(0.1)
    t1 = time.monotonic()

    if not os.path.ismount(mnt):
        print("mount never came up within 10s", file=sys.stderr)
        _unmount(mnt)
        return 1

    print(f"mount established in {t1 - t0:.2f}s (target: <=3s)")
    print()
    print("top-level listing (first 10 entries):")
    try:
        for name in sorted(os.listdir(mnt))[:10]:
            print(f"  {name}")
    except OSError as exc:
        print(f"  listing failed: {exc}")

    print()
    print("mount staying up; press Ctrl-C to unmount.")
    try:
        while fuse_thread.is_alive():
            fuse_thread.join(timeout=1.0)
    except KeyboardInterrupt:
        print("\nunmounting ...")
    finally:
        _unmount(mnt)
        _report_orphans()
    return 0


def _unmount(mnt: Path) -> None:
    for args in (["fusermount", "-u", str(mnt)], ["umount", str(mnt)]):
        with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
            subprocess.run(args, check=False, capture_output=True, timeout=5)
    with contextlib.suppress(OSError):
        mnt.rmdir()


def _report_orphans() -> None:
    # pgrep -x matches the exact process name only (i.e. the s3fs-fuse or
    # rclone binaries themselves) — not any shell whose command line happens
    # to contain "s3fs". Python s3fs runs in-process so a clean result here
    # means zero orphans for this backend.
    for name in ("s3fs", "rclone"):
        with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
            result = subprocess.run(
                ["pgrep", "-x", name],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            out = result.stdout.strip() or "none"
            print(f"orphans ({name} binary): {out}")


if __name__ == "__main__":
    raise SystemExit(main())
