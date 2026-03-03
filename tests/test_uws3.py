"""Tests for the UWS3 wrapper class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from uw_s3 import UWS3, CAMPUS_ENDPOINT, WEB_ENDPOINT


def test_campus_factory() -> None:
    with patch("uw_s3.Minio"):
        client = UWS3.campus("key", "secret")
        assert client.endpoint == CAMPUS_ENDPOINT


def test_web_factory() -> None:
    with patch("uw_s3.Minio"):
        client = UWS3.web("key", "secret")
        assert client.endpoint == WEB_ENDPOINT


def test_default_bucket() -> None:
    assert UWS3.default_bucket("jdoe") == "jdoe-bucket-01"


def test_list_buckets() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        b1, b2 = MagicMock(), MagicMock()
        b1.name = "bucket-a"
        b2.name = "bucket-b"
        mock.list_buckets.return_value = [b1, b2]

        client = UWS3("key", "secret")
        assert client.list_buckets() == ["bucket-a", "bucket-b"]


def test_list_objects() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        obj = MagicMock()
        obj.object_name = "file.txt"
        mock.list_objects.return_value = [obj]

        client = UWS3("key", "secret")
        assert client.list_objects("bucket") == ["file.txt"]


def test_list_objects_with_size() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        obj = MagicMock()
        obj.object_name = "file.txt"
        obj.size = 42
        mock.list_objects.return_value = [obj]

        client = UWS3("key", "secret")
        result = client.list_objects_with_size("bucket")
        assert result == [("file.txt", 42)]


def test_exists_true() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        mock.stat_object.return_value = MagicMock()

        client = UWS3("key", "secret")
        assert client.exists("bucket", "file.txt") is True


def test_exists_false() -> None:
    from minio.error import S3Error

    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        mock.stat_object.side_effect = S3Error(
            "NoSuchKey", "NoSuchKey", "resource", "", "", ""
        )

        client = UWS3("key", "secret")
        assert client.exists("bucket", "file.txt") is False


def test_bucket_exists() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        mock.bucket_exists.return_value = True

        client = UWS3("key", "secret")
        assert client.bucket_exists("my-bucket") is True
