"""Tests for the UWS3 wrapper class."""

from unittest.mock import MagicMock, patch

from uw_s3 import UWS3


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


def test_bucket_exists() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        mock.bucket_exists.return_value = True

        client = UWS3("key", "secret")
        assert client.bucket_exists("my-bucket") is True
