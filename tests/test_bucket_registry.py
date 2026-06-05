"""Tests for the bucket -> endpoint registry."""

from __future__ import annotations

from pathlib import Path

import pytest

import uw_s3.bucket_registry as reg
from uw_s3.bucket_registry import (
    CAMPUS_ENDPOINT,
    WEB_ENDPOINT,
    BucketRegistry,
)


@pytest.fixture
def buckets_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_file = tmp_path / "buckets.json"
    monkeypatch.setattr(reg, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(reg, "CONFIG_FILE", config_file)
    return config_file


def test_load_empty_when_no_file(buckets_file: Path) -> None:
    assert BucketRegistry.load().bucket_names() == []


def test_save_load_roundtrip(buckets_file: Path) -> None:
    r = BucketRegistry({"a": CAMPUS_ENDPOINT, "b": WEB_ENDPOINT})
    r.save()
    loaded = BucketRegistry.load()
    assert loaded.endpoint_for("a") == CAMPUS_ENDPOINT
    assert loaded.endpoint_for("b") == WEB_ENDPOINT


def test_load_ignores_unknown_endpoints(buckets_file: Path) -> None:
    buckets_file.write_text('{"a": "campus.s3.wisc.edu", "b": "bogus"}')
    loaded = BucketRegistry.load()
    assert loaded.bucket_names() == ["a"]


def test_merge_probe_records_listed_buckets(buckets_file: Path) -> None:
    r = BucketRegistry()
    r.merge_probe(
        {CAMPUS_ENDPOINT, WEB_ENDPOINT},
        {CAMPUS_ENDPOINT: ["c1"], WEB_ENDPOINT: ["w1", "w2"]},
    )
    assert r.endpoint_for("c1") == CAMPUS_ENDPOINT
    assert r.endpoint_for("w2") == WEB_ENDPOINT
    assert r.is_reachable("c1") is True


def test_merge_probe_keeps_unreachable_entries(buckets_file: Path) -> None:
    # campus bucket known from before; now only web is reachable.
    r = BucketRegistry({"campus-only": CAMPUS_ENDPOINT})
    r.merge_probe({WEB_ENDPOINT}, {WEB_ENDPOINT: ["w1"]})
    assert r.endpoint_for("campus-only") == CAMPUS_ENDPOINT
    assert r.is_reachable("campus-only") is False
    assert r.is_reachable("w1") is True


def test_merge_probe_drops_deleted_reachable_bucket(buckets_file: Path) -> None:
    r = BucketRegistry({"gone": WEB_ENDPOINT, "stays": WEB_ENDPOINT})
    # web reachable and lists only "stays" -> "gone" was deleted.
    r.merge_probe({WEB_ENDPOINT}, {WEB_ENDPOINT: ["stays"]})
    assert r.endpoint_for("gone") is None
    assert r.endpoint_for("stays") == WEB_ENDPOINT


def test_entries_annotates_reachability(buckets_file: Path) -> None:
    r = BucketRegistry(
        {"c1": CAMPUS_ENDPOINT, "w1": WEB_ENDPOINT},
        reachable={WEB_ENDPOINT},
    )
    by_name = {e.name: e for e in r.entries()}
    assert by_name["w1"].reachable is True
    assert by_name["c1"].reachable is False
    # entries() is sorted by name
    assert [e.name for e in r.entries()] == ["c1", "w1"]


def test_register_and_remove_persist(buckets_file: Path) -> None:
    r = BucketRegistry()
    r.register("new", WEB_ENDPOINT)
    assert BucketRegistry.load().endpoint_for("new") == WEB_ENDPOINT
    assert r.is_reachable("new") is True
    r.remove("new")
    assert BucketRegistry.load().endpoint_for("new") is None
