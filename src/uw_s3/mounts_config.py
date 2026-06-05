"""Persist detached-mount metadata to ~/.config/uw-s3/mounts.json.

Stores only `{bucket, endpoint, mount_point, pid, started_at}` per I-3 and
Constitution §9: S3 credentials MUST NEVER be persisted here.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "uw-s3"
CONFIG_FILE = CONFIG_DIR / "mounts.json"


@dataclass
class MountRecord:
    """Metadata for a single detached mount worker."""

    bucket: str
    endpoint: str
    mount_point: str
    pid: int
    started_at: float


def load() -> list[MountRecord]:
    """Load all persisted mount records."""
    if not CONFIG_FILE.exists():
        return []
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError, OSError:
        return []
    return [MountRecord(**entry) for entry in data]


def save(records: list[MountRecord]) -> None:
    """Overwrite the mounts file with the given records."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps([asdict(r) for r in records], indent=2))


def add(record: MountRecord) -> None:
    """Add a record (replaces any existing entry with the same bucket+mount_point)."""
    existing = [
        r
        for r in load()
        if not (r.bucket == record.bucket and r.mount_point == record.mount_point)
    ]
    existing.append(record)
    save(existing)


def remove(bucket: str, mount_point: str) -> None:
    """Remove the record matching bucket + mount_point if present."""
    save(
        [r for r in load() if not (r.bucket == bucket and r.mount_point == mount_point)]
    )


def _is_process_alive(pid: int) -> bool:
    """True if signal 0 to pid succeeds (process exists and is signalable)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def is_record_live(record: MountRecord) -> bool:
    """True if the worker PID is alive AND its mount point still reports as mounted."""
    return _is_process_alive(record.pid) and os.path.ismount(record.mount_point)


def clear_dead() -> list[MountRecord]:
    """Drop records whose worker is gone or whose mount point is unmounted.

    Returns the dropped records so the caller can run defensive cleanup
    (e.g., `fusermount -u`) on each stale mount point.
    """
    all_records = load()
    live = [r for r in all_records if is_record_live(r)]
    dead = [r for r in all_records if not is_record_live(r)]
    if dead:
        save(live)
    return dead
