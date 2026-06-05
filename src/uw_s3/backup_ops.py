"""Programmatic backup/restore operations — headless reuse of the sync core.

backup = push/upload (local -> S3); restore = pull/download (S3 -> local).
Both auto-detect single file vs folder and reuse SyncEngine for incremental
(size-based) folder transfers.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT, UWS3
from uw_s3.sync.engine import SyncAction, SyncEngine
from uw_s3.sync.models import SyncMap
from uw_s3.validators import BUCKET_NAME_RE

OnFile = Callable[[str], None]


@dataclass
class BackupResult:
    """Outcome of a backup or restore operation."""

    transferred: int
    skipped: int
    bytes: int
    paths: list[str]
    dry_run: bool


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse an ``s3://bucket/key`` URI into ``(bucket, key)``."""
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an s3:// URI: {uri!r}")
    bucket, _, key = uri[len("s3://") :].partition("/")
    if not BUCKET_NAME_RE.match(bucket):
        raise ValueError(f"Invalid bucket name: {bucket!r}")
    return bucket, key


def _resolve_endpoint(name: str | None) -> str:
    """Map a 'campus'/'web' name to its endpoint constant (default campus)."""
    return WEB_ENDPOINT if (name or "").lower() == "web" else CAMPUS_ENDPOINT


def _callback(on_file: OnFile | None) -> Callable[[SyncAction], object] | None:
    if on_file is None:
        return None
    return lambda action: on_file(action.relative_path)


def run_backup(
    client: UWS3,
    local_path: Path,
    bucket: str,
    key: str,
    *,
    endpoint: str = CAMPUS_ENDPOINT,
    dry_run: bool = False,
    on_file: OnFile | None = None,
) -> BackupResult:
    """Upload a file or folder to S3. Folders sync incrementally by size."""
    if not local_path.exists():
        raise FileNotFoundError(f"Local path does not exist: {local_path}")

    if local_path.is_dir():
        mapping = SyncMap(
            local_dir=str(local_path), bucket=bucket, prefix=key, endpoint=endpoint
        )
        engine = SyncEngine(client, mapping)
        summary = engine.summary_push()
        total_bytes = sum(
            (local_path / a.relative_path).stat().st_size for a in summary.actions
        )
        if not dry_run:
            engine.push(callback=_callback(on_file), actions=summary.actions)
        return BackupResult(
            transferred=summary.to_transfer,
            skipped=summary.in_sync,
            bytes=total_bytes,
            paths=[a.relative_path for a in summary.actions],
            dry_run=dry_run,
        )

    size = local_path.stat().st_size
    if not dry_run:
        client.upload_file(bucket, key, local_path)
        if on_file:
            on_file(key)
    return BackupResult(
        transferred=1, skipped=0, bytes=size, paths=[key], dry_run=dry_run
    )


def run_restore(
    client: UWS3,
    bucket: str,
    key: str,
    local_path: Path,
    *,
    endpoint: str = CAMPUS_ENDPOINT,
    dry_run: bool = False,
    on_file: OnFile | None = None,
) -> BackupResult:
    """Download a file or folder from S3. Folders sync incrementally by size."""
    objects = client.list_objects_with_size(bucket, prefix=key, recursive=True)
    if not objects:
        raise FileNotFoundError(f"No objects found at s3://{bucket}/{key}")

    single = len(objects) == 1 and objects[0][0] == key and not key.endswith("/")
    if single:
        dest = local_path / Path(key).name if local_path.is_dir() else local_path
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(bucket, key, dest)
            if on_file:
                on_file(str(dest))
        return BackupResult(
            transferred=1,
            skipped=0,
            bytes=objects[0][1],
            paths=[str(dest)],
            dry_run=dry_run,
        )

    mapping = SyncMap(
        local_dir=str(local_path), bucket=bucket, prefix=key, endpoint=endpoint
    )
    engine = SyncEngine(client, mapping)
    summary = engine.summary_pull()
    prefix = f"{key.rstrip('/')}/" if key.rstrip("/") else ""
    remote_sizes = {
        (name[len(prefix) :] if prefix and name.startswith(prefix) else name): size
        for name, size in objects
    }
    total_bytes = sum(remote_sizes.get(a.relative_path, 0) for a in summary.actions)
    if not dry_run:
        engine.pull(callback=_callback(on_file), actions=summary.actions)
    return BackupResult(
        transferred=summary.to_transfer,
        skipped=summary.in_sync,
        bytes=total_bytes,
        paths=[a.relative_path for a in summary.actions],
        dry_run=dry_run,
    )
