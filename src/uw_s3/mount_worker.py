"""Single-purpose detached mount worker (Constitution §10).

Spawned by the TUI as `python -m uw_s3.mount_worker --bucket X ...`. Holds
one FUSE mount in this process, then blocks until SIGTERM/SIGINT, at which
point it unmounts cleanly and exits 0. Reads credentials only from the
environment (`S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`); §9 forbids the
worker from reading creds off disk or persisting them.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading

from uw_s3.mount_backend import Mount


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uws3-mount-worker",
        description="Detached FUSE mount worker for uw-s3 (Constitution §10).",
    )
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--mount-point", required=True)
    parser.add_argument(
        "--marker",
        default="uws3-mount-worker",
        help="Cosmetic marker so `pgrep -f uws3-mount-worker` finds this process.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    access_key = os.environ.get("S3_ACCESS_KEY_ID", "")
    secret_key = os.environ.get("S3_SECRET_ACCESS_KEY", "")
    if not access_key or not secret_key:
        print(
            "uws3-mount-worker: S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY missing in env",
            file=sys.stderr,
        )
        return 2

    mount = Mount(
        access_key=access_key,
        secret_key=secret_key,
        endpoint=args.endpoint,
        bucket=args.bucket,
        mount_point=args.mount_point,
    )

    try:
        mount.mount()
    except Exception as exc:
        print(f"uws3-mount-worker: mount failed: {exc}", file=sys.stderr)
        return 1

    stop = threading.Event()

    def _handle_signal(signum: int, frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    stop.wait()

    try:
        mount.unmount()
    except Exception as exc:
        print(f"uws3-mount-worker: unmount error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
