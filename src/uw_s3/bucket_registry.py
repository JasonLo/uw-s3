"""Remember which endpoint each bucket lives on.

UW buckets are partitioned by domain: a bucket created against
``campus.s3.wisc.edu`` is reachable only on the UW network/VPN, while a
``web.s3.wisc.edu`` bucket is reachable from anywhere. This registry caches the
bucket -> endpoint map to ``~/.config/uw-s3/buckets.json`` so operations route
automatically and the app still knows about buckets whose endpoint is currently
unreachable. Per Constitution §9, S3 credentials MUST NEVER be persisted here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from uw_s3.client import CAMPUS_ENDPOINT, WEB_ENDPOINT

ENDPOINTS: tuple[str, ...] = (CAMPUS_ENDPOINT, WEB_ENDPOINT)

CONFIG_DIR = Path.home() / ".config" / "uw-s3"
CONFIG_FILE = CONFIG_DIR / "buckets.json"


@dataclass
class BucketEntry:
    """A bucket, the endpoint it lives on, and whether that endpoint is up now."""

    name: str
    endpoint: str
    reachable: bool


def _load_map() -> dict[str, str]:
    """Load the persisted bucket -> endpoint map, or empty if missing/corrupt."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except json.JSONDecodeError, OSError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if v in ENDPOINTS}


class BucketRegistry:
    """In-memory bucket -> endpoint map with disk persistence and probe merging."""

    def __init__(
        self,
        mapping: dict[str, str] | None = None,
        reachable: set[str] | None = None,
    ) -> None:
        self._map: dict[str, str] = dict(mapping or {})
        self._reachable: set[str] = set(reachable or set())

    @classmethod
    def load(cls) -> BucketRegistry:
        """Build a registry from the persisted map (nothing reachable yet)."""
        return cls(mapping=_load_map())

    def save(self) -> None:
        """Persist the current bucket -> endpoint map."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self._map, indent=2, sort_keys=True))

    def merge_probe(
        self,
        reachable_endpoints: set[str],
        union: set[str],
        homes: dict[str, str],
    ) -> None:
        """Fold a fresh probe into the map.

        ``list_buckets`` returns the same global union of names on *every*
        endpoint, so it cannot tell where a bucket lives; only ``bucket_exists``
        (HEAD bucket) discriminates. The probe therefore passes the ``union`` of
        all visible names plus ``homes`` — the bucket -> endpoint pairs it could
        confirm via ``bucket_exists`` on a reachable endpoint.

        Confirmed homes are authoritative (this corrects buckets that were
        previously mis-pinned). A bucket in the union whose home could not be
        confirmed (it lives on an unreachable endpoint) keeps its cached home, or
        is inferred to the sole unreachable endpoint — so campus buckets survive
        and stay routable while off-VPN. Buckets absent from the union were
        deleted and are dropped. When nothing is reachable the cache is left
        untouched.
        """
        self._reachable = set(reachable_endpoints)
        if not reachable_endpoints:
            return
        unreachable = [e for e in ENDPOINTS if e not in reachable_endpoints]
        new_map: dict[str, str] = {}
        for bucket in union:
            if bucket in homes:
                new_map[bucket] = homes[bucket]
            elif bucket in self._map:
                new_map[bucket] = self._map[bucket]
            elif len(unreachable) == 1:
                new_map[bucket] = unreachable[0]
        self._map = new_map
        self.save()

    def endpoint_for(self, bucket: str) -> str | None:
        """Return the endpoint a bucket lives on, or None if unknown."""
        return self._map.get(bucket)

    def is_reachable(self, bucket: str) -> bool:
        """True if the bucket's endpoint was reachable in the last probe."""
        endpoint = self._map.get(bucket)
        return endpoint is not None and endpoint in self._reachable

    @property
    def reachable_endpoints(self) -> set[str]:
        """The set of endpoints reachable as of the last probe."""
        return set(self._reachable)

    def entries(self) -> list[BucketEntry]:
        """All known buckets, annotated with reachability, sorted by name."""
        return [
            BucketEntry(name=name, endpoint=ep, reachable=ep in self._reachable)
            for name, ep in sorted(self._map.items())
        ]

    def bucket_names(self) -> list[str]:
        """All known bucket names, sorted."""
        return sorted(self._map)

    def register(self, bucket: str, endpoint: str) -> None:
        """Record a (usually just-created) bucket's endpoint and persist."""
        self._map[bucket] = endpoint
        self._reachable.add(endpoint)
        self.save()

    def remove(self, bucket: str) -> None:
        """Forget a (usually just-deleted) bucket and persist."""
        if self._map.pop(bucket, None) is not None:
            self.save()
