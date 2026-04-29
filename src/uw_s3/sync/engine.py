"""Sync engine — push/pull files between a local directory and S3."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from uw_s3 import UWS3
from uw_s3.sync.models import SyncMap


@dataclass
class SyncAction:
    """A single file to transfer."""

    relative_path: str
    direction: Literal["push", "pull"]
    reason: str  # e.g. "missing on S3", "size differs"


@dataclass
class SyncSummary:
    """Aggregate result of a dry-run diff between local and remote."""

    actions: list[SyncAction]
    in_sync: int
    new: int
    size_differs: int

    @property
    def to_transfer(self) -> int:
        return len(self.actions)


class SyncEngine:
    """Simple push/pull sync between a local folder and an S3 bucket."""

    def __init__(self, client: UWS3, mapping: SyncMap) -> None:
        self.client = client
        self.mapping = mapping
        self.local = Path(mapping.local_dir)

    def _object_key(self, rel_path: str) -> str:
        """Build the full S3 object key for a relative path."""
        prefix = self.mapping.prefix.rstrip("/")
        if prefix:
            return f"{prefix}/{rel_path}"
        return rel_path

    def _local_files(self) -> dict[str, int]:
        """Return {relative_posix_path: size} for all files in local dir."""
        result: dict[str, int] = {}
        for p in self.local.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self.local).as_posix()
                result[rel] = p.stat().st_size
        return result

    def _remote_objects(self) -> dict[str, int]:
        """Return {relative_path: size} for all objects under the prefix."""
        prefix = self.mapping.prefix.rstrip("/")
        prefix_with_slash = f"{prefix}/" if prefix else ""
        result: dict[str, int] = {}
        for name, size in self.client.list_objects_with_size(
            self.mapping.bucket, prefix=prefix_with_slash, recursive=True
        ):
            if prefix_with_slash and name.startswith(prefix_with_slash):
                name = name[len(prefix_with_slash) :]
            result[name] = size
        return result

    def _diff(self, direction: Literal["push", "pull"]) -> SyncSummary:
        """Compute a sync summary for the given direction."""
        local = self._local_files()
        remote = self._remote_objects()
        if direction == "push":
            source, dest = local, remote
            missing_reason = "missing on S3"
        else:
            source, dest = remote, local
            missing_reason = "missing locally"
        actions: list[SyncAction] = []
        in_sync = 0
        new = 0
        size_differs = 0
        for rel, size in sorted(source.items()):
            if rel not in dest:
                actions.append(SyncAction(rel, direction, missing_reason))
                new += 1
            elif dest[rel] != size:
                actions.append(SyncAction(rel, direction, "size differs"))
                size_differs += 1
            else:
                in_sync += 1
        return SyncSummary(
            actions=actions, in_sync=in_sync, new=new, size_differs=size_differs
        )

    def summary_push(self) -> SyncSummary:
        """Dry-run: summary of what would be pushed (local → S3)."""
        return self._diff("push")

    def summary_pull(self) -> SyncSummary:
        """Dry-run: summary of what would be pulled (S3 → local)."""
        return self._diff("pull")

    def status_push(self) -> list[SyncAction]:
        """Dry-run: what would be pushed (local → S3)."""
        return self.summary_push().actions

    def status_pull(self) -> list[SyncAction]:
        """Dry-run: what would be pulled (S3 → local)."""
        return self.summary_pull().actions

    def push(
        self,
        callback: Callable[[SyncAction], object] | None = None,
        actions: list[SyncAction] | None = None,
    ) -> list[SyncAction]:
        """Upload local files that are new or differ in size."""
        if actions is None:
            actions = self.status_push()
        for action in actions:
            local_path = self.local / action.relative_path
            key = self._object_key(action.relative_path)
            self.client.upload_file(self.mapping.bucket, key, local_path)
            if callback:
                callback(action)
        return actions

    def pull(
        self,
        callback: Callable[[SyncAction], object] | None = None,
        actions: list[SyncAction] | None = None,
    ) -> list[SyncAction]:
        """Download S3 objects that are new or differ in size."""
        if actions is None:
            actions = self.status_pull()
        for action in actions:
            local_path = self.local / action.relative_path
            local_path.parent.mkdir(parents=True, exist_ok=True)
            key = self._object_key(action.relative_path)
            self.client.download_file(self.mapping.bucket, key, local_path)
            if callback:
                callback(action)
        return actions
