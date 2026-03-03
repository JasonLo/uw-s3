"""Tests for sync map data model."""

from __future__ import annotations

from uw_s3.sync.models import SyncMap


def test_syncmap_auto_generates_id() -> None:
    m = SyncMap(local_dir="/tmp/data", bucket="my-bucket")
    assert m.id
    assert len(m.id) == 12


def test_syncmap_same_inputs_same_id() -> None:
    a = SyncMap(local_dir="/tmp/data", bucket="my-bucket", prefix="p")
    b = SyncMap(local_dir="/tmp/data", bucket="my-bucket", prefix="p")
    assert a.id == b.id


def test_syncmap_different_inputs_different_id() -> None:
    a = SyncMap(local_dir="/tmp/a", bucket="my-bucket")
    b = SyncMap(local_dir="/tmp/b", bucket="my-bucket")
    assert a.id != b.id


def test_syncmap_explicit_id_not_overwritten() -> None:
    m = SyncMap(local_dir="/tmp/data", bucket="b", id="custom-id")
    assert m.id == "custom-id"


def test_syncmap_default_endpoint() -> None:
    m = SyncMap(local_dir="/tmp/data", bucket="b")
    assert m.endpoint == "campus.s3.wisc.edu"


def test_syncmap_prefix_affects_id() -> None:
    a = SyncMap(local_dir="/tmp/data", bucket="b", prefix="")
    b = SyncMap(local_dir="/tmp/data", bucket="b", prefix="subdir")
    assert a.id != b.id
