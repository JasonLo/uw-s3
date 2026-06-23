"""Route each bucket operation to the endpoint that bucket lives on.

`S3Router` replaces the single endpoint-bound `UWS3` the app used to hold. It
owns one `UWS3` per endpoint plus a `BucketRegistry`, probes which endpoints the
machine can reach, and dispatches every bucket-scoped call to the right client.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path

from uw_s3.bucket_registry import ENDPOINTS, BucketEntry, BucketRegistry
from uw_s3.client import CAMPUS_ENDPOINT, WEB_ENDPOINT, ObjectInfo, UWS3

_PROBE_TIMEOUT = 2.0


class EndpointUnreachable(RuntimeError):
    """Raised when a bucket's endpoint is not reachable from this machine."""


def _vpn_hint(endpoint: str) -> str:
    """A human-readable reason a given endpoint can't be used right now."""
    if endpoint == CAMPUS_ENDPOINT:
        return "it lives on the campus endpoint — connect to the UW network or VPN"
    return "its endpoint (web) is unreachable — check your internet connection"


def _tcp_reachable(host: str, port: int = 443, timeout: float = _PROBE_TIMEOUT) -> bool:
    """True if a TCP connection to host:port succeeds within `timeout`."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class S3Router:
    """Endpoint-aware facade over per-endpoint `UWS3` clients."""

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        *,
        registry: BucketRegistry | None = None,
        connect_timeout: float = _PROBE_TIMEOUT,
    ) -> None:
        self._access_key = access_key
        self._secret_key = secret_key
        self.registry = registry if registry is not None else BucketRegistry.load()
        self.connect_timeout = connect_timeout
        self._clients: dict[str, UWS3] = {}
        self.probe_errors: dict[str, str] = {}

    # --- client management -------------------------------------------------

    def client(self, endpoint: str) -> UWS3:
        """Return (building once) the `UWS3` bound to a specific endpoint."""
        if endpoint not in self._clients:
            self._clients[endpoint] = UWS3(
                self._access_key, self._secret_key, endpoint=endpoint
            )
        return self._clients[endpoint]

    def client_for(self, bucket: str) -> UWS3:
        """Return the client for a bucket, or raise if its endpoint is down."""
        endpoint = self.registry.endpoint_for(bucket)
        if endpoint is None:
            raise EndpointUnreachable(f"Unknown bucket {bucket!r} — try Refresh.")
        if endpoint not in self.registry.reachable_endpoints:
            raise EndpointUnreachable(
                f"Cannot reach {bucket!r}: {_vpn_hint(endpoint)}."
            )
        return self.client(endpoint)

    # --- probing -----------------------------------------------------------

    def probe(self) -> None:
        """Detect reachable endpoints and refresh the registry. Blocking — run
        on a worker thread (Constitution §4)."""
        reachable: set[str] = set()
        union: set[str] = set()
        errors: dict[str, str] = {}
        for endpoint in ENDPOINTS:
            if not _tcp_reachable(endpoint, timeout=self.connect_timeout):
                errors[endpoint] = "unreachable"
                continue
            try:
                union.update(self.client(endpoint).list_buckets())
                reachable.add(endpoint)
            except Exception as exc:
                errors[endpoint] = str(exc)
        # list_buckets returns the same global union on every endpoint, so it
        # can't reveal where a bucket lives. bucket_exists (HEAD bucket) can: a
        # campus bucket 404s on web and vice versa. Probe each name to find home.
        homes: dict[str, str] = {}
        for bucket in union:
            for endpoint in reachable:
                try:
                    if self.client(endpoint).bucket_exists(bucket):
                        homes[bucket] = endpoint
                        break
                except Exception:
                    continue
        self.probe_errors = errors
        self.registry.merge_probe(reachable, union, homes)

    @property
    def reachable_endpoints(self) -> set[str]:
        return self.registry.reachable_endpoints

    def endpoint_for(self, bucket: str) -> str | None:
        return self.registry.endpoint_for(bucket)

    def is_reachable(self, bucket: str) -> bool:
        return self.registry.is_reachable(bucket)

    # --- bucket listing ----------------------------------------------------

    def list_buckets(self) -> list[str]:
        """All known bucket names across endpoints (the union)."""
        return self.registry.bucket_names()

    def entries(self) -> list[BucketEntry]:
        """All known buckets annotated with endpoint + reachability."""
        return self.registry.entries()

    # --- bucket lifecycle --------------------------------------------------

    def bucket_exists(self, bucket: str, *, endpoint: str | None = None) -> bool:
        """Check existence on a given endpoint (for new names) or by route."""
        target = endpoint or self.registry.endpoint_for(bucket)
        if target is None:
            return False
        return self.client(target).bucket_exists(bucket)

    def create_bucket(self, bucket: str, *, endpoint: str) -> None:
        """Create a bucket on `endpoint` and register its location."""
        self.client(endpoint).create_bucket(bucket)
        self.registry.register(bucket, endpoint)

    def delete_bucket(self, bucket: str) -> None:
        self.client_for(bucket).delete_bucket(bucket)
        self.registry.remove(bucket)

    def empty_bucket(self, bucket: str) -> None:
        self.client_for(bucket).empty_bucket(bucket)

    def set_bucket_policy(self, bucket: str, permission: str) -> None:
        self.client_for(bucket).set_bucket_policy(bucket, permission)

    # --- object operations (routed by bucket) ------------------------------

    def list_objects(
        self, bucket: str, *, prefix: str = "", recursive: bool = True
    ) -> list[str]:
        return self.client_for(bucket).list_objects(
            bucket, prefix=prefix, recursive=recursive
        )

    def list_objects_with_size(
        self, bucket: str, *, prefix: str = "", recursive: bool = True
    ) -> list[tuple[str, int]]:
        return self.client_for(bucket).list_objects_with_size(
            bucket, prefix=prefix, recursive=recursive
        )

    def iter_objects_with_size(
        self, bucket: str, *, prefix: str = "", recursive: bool = True
    ) -> Iterator[tuple[str, int]]:
        return self.client_for(bucket).iter_objects_with_size(
            bucket, prefix=prefix, recursive=recursive
        )

    def list_objects_detail(
        self, bucket: str, *, prefix: str = "", recursive: bool = True
    ) -> list[ObjectInfo]:
        return self.client_for(bucket).list_objects_detail(
            bucket, prefix=prefix, recursive=recursive
        )

    def upload_file(self, bucket: str, object_name: str, file_path: str | Path) -> None:
        self.client_for(bucket).upload_file(bucket, object_name, file_path)

    def download_file(
        self, bucket: str, object_name: str, file_path: str | Path
    ) -> None:
        self.client_for(bucket).download_file(bucket, object_name, file_path)

    def delete_object(self, bucket: str, object_name: str) -> None:
        self.client_for(bucket).delete_object(bucket, object_name)

    def delete_prefix(self, bucket: str, prefix: str) -> int:
        return self.client_for(bucket).delete_prefix(bucket, prefix)

    def rename_object(self, bucket: str, old_key: str, new_key: str) -> None:
        self.client_for(bucket).rename_object(bucket, old_key, new_key)

    def rename_prefix(self, bucket: str, old_prefix: str, new_prefix: str) -> int:
        return self.client_for(bucket).rename_prefix(bucket, old_prefix, new_prefix)


__all__ = ["S3Router", "EndpointUnreachable", "CAMPUS_ENDPOINT", "WEB_ENDPOINT"]
