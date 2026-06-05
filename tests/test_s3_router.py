"""Tests for the endpoint-routing S3 facade."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import uw_s3.bucket_registry as reg
from uw_s3.bucket_registry import CAMPUS_ENDPOINT, WEB_ENDPOINT, BucketRegistry
from uw_s3.s3_router import EndpointUnreachable, S3Router


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock Minio for the whole test and keep registry.save() off the real file.

    Minio must stay mocked for the entire test (not just construction): the
    router builds per-endpoint clients lazily, so a real Minio would otherwise
    make a real network call on the first routed/probed operation.
    """
    monkeypatch.setattr("uw_s3.client.Minio", MagicMock)
    monkeypatch.setattr(reg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(reg, "CONFIG_FILE", tmp_path / "buckets.json")


def _router(mapping: dict[str, str], reachable: set[str]) -> S3Router:
    """Build a router over a pre-populated registry (Minio mocked by fixture)."""
    registry = BucketRegistry(mapping, reachable=reachable)
    return S3Router("key", "secret", registry=registry)


def test_client_for_routes_to_correct_endpoint() -> None:
    router = _router(
        {"camp": CAMPUS_ENDPOINT, "web": WEB_ENDPOINT},
        {CAMPUS_ENDPOINT, WEB_ENDPOINT},
    )
    assert router.client_for("camp").endpoint == CAMPUS_ENDPOINT
    assert router.client_for("web").endpoint == WEB_ENDPOINT
    # same endpoint -> same cached client instance
    assert router.client_for("camp") is router.client(CAMPUS_ENDPOINT)


def test_client_for_unknown_bucket_raises() -> None:
    router = _router({}, set())
    with pytest.raises(EndpointUnreachable, match="Unknown bucket"):
        router.client_for("nope")


def test_client_for_unreachable_endpoint_raises_with_hint() -> None:
    router = _router({"camp": CAMPUS_ENDPOINT}, reachable=set())
    with pytest.raises(EndpointUnreachable, match="UW network or VPN"):
        router.client_for("camp")


def test_list_buckets_returns_union() -> None:
    router = _router({"camp": CAMPUS_ENDPOINT, "web": WEB_ENDPOINT}, {WEB_ENDPOINT})
    assert router.list_buckets() == ["camp", "web"]


def test_object_op_routes_to_endpoint_client() -> None:
    router = _router({"web": WEB_ENDPOINT}, {WEB_ENDPOINT})
    client = router.client(WEB_ENDPOINT)
    client.upload_file = MagicMock()
    router.upload_file("web", "k", "/tmp/f")
    client.upload_file.assert_called_once_with("web", "k", "/tmp/f")


def test_create_bucket_registers_endpoint() -> None:
    router = _router({}, set())
    client = router.client(WEB_ENDPOINT)
    client.create_bucket = MagicMock()
    router.create_bucket("fresh", endpoint=WEB_ENDPOINT)
    client.create_bucket.assert_called_once_with("fresh")
    assert router.endpoint_for("fresh") == WEB_ENDPOINT
    assert router.is_reachable("fresh") is True


def test_delete_bucket_unregisters() -> None:
    router = _router({"web": WEB_ENDPOINT}, {WEB_ENDPOINT})
    router.client(WEB_ENDPOINT).delete_bucket = MagicMock()
    router.delete_bucket("web")
    assert router.endpoint_for("web") is None


def test_probe_merges_reachable_and_lists() -> None:
    router = _router({}, set())

    def fake_reachable(host: str, port: int = 443, timeout: float = 2.0) -> bool:
        return host == WEB_ENDPOINT  # only web reachable (off VPN)

    web_client = router.client(WEB_ENDPOINT)
    web_client.list_buckets = MagicMock(return_value=["w1", "w2"])

    with patch("uw_s3.s3_router._tcp_reachable", side_effect=fake_reachable):
        router.probe()

    assert router.reachable_endpoints == {WEB_ENDPOINT}
    assert router.endpoint_for("w1") == WEB_ENDPOINT
    assert CAMPUS_ENDPOINT in router.probe_errors


def test_probe_records_error_when_listing_fails() -> None:
    router = _router({}, set())
    router.client(WEB_ENDPOINT).list_buckets = MagicMock(
        side_effect=RuntimeError("bad creds")
    )
    with patch("uw_s3.s3_router._tcp_reachable", return_value=True):
        router.probe()
    assert WEB_ENDPOINT not in router.reachable_endpoints
    assert "bad creds" in router.probe_errors[WEB_ENDPOINT]
