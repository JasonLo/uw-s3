"""Tests for the UWS3 wrapper class."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from uw_s3 import UWS3, ObjectInfo


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


def test_list_objects_with_size_none_becomes_zero() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        obj = MagicMock()
        obj.object_name = "file.txt"
        obj.size = None
        mock.list_objects.return_value = [obj]

        client = UWS3("key", "secret")
        assert client.list_objects_with_size("bucket") == [("file.txt", 0)]


def test_list_objects_detail() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        ts = datetime(2025, 1, 1, tzinfo=timezone.utc)
        obj = MagicMock()
        obj.object_name = "report.csv"
        obj.size = 1024
        obj.last_modified = ts
        mock.list_objects.return_value = [obj]

        client = UWS3("key", "secret")
        result = client.list_objects_detail("bucket")
        assert len(result) == 1
        assert result[0] == ObjectInfo(name="report.csv", size=1024, last_modified=ts)


def test_list_objects_detail_null_size() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        obj = MagicMock()
        obj.object_name = "empty.bin"
        obj.size = None
        obj.last_modified = None
        mock.list_objects.return_value = [obj]

        client = UWS3("key", "secret")
        result = client.list_objects_detail("bucket")
        assert result[0].size == 0
        assert result[0].last_modified is None


def test_bucket_exists() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        mock.bucket_exists.return_value = True

        client = UWS3("key", "secret")
        assert client.bucket_exists("my-bucket") is True


def test_create_bucket() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        client = UWS3("key", "secret")
        client.create_bucket("new-bucket")
        mock.make_bucket.assert_called_once_with("new-bucket")


def test_delete_bucket() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        client = UWS3("key", "secret")
        client.delete_bucket("old-bucket")
        mock.remove_bucket.assert_called_once_with("old-bucket")


def test_empty_bucket_with_objects() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        o1, o2 = MagicMock(), MagicMock()
        o1.object_name = "a.txt"
        o2.object_name = "b.txt"
        mock.list_objects.return_value = [o1, o2]
        mock.remove_objects.return_value = iter([])

        client = UWS3("key", "secret")
        client.empty_bucket("bucket")
        mock.remove_objects.assert_called_once()


def test_empty_bucket_no_objects() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        mock.list_objects.return_value = []

        client = UWS3("key", "secret")
        client.empty_bucket("bucket")
        mock.remove_objects.assert_not_called()


def test_empty_bucket_error_raises() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        obj = MagicMock()
        obj.object_name = "file.txt"
        mock.list_objects.return_value = [obj]
        err = MagicMock()
        err.message = "access denied"
        mock.remove_objects.return_value = iter([err])

        client = UWS3("key", "secret")
        with pytest.raises(RuntimeError, match="access denied"):
            client.empty_bucket("bucket")


def test_set_bucket_policy_private() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        client = UWS3("key", "secret")
        client.set_bucket_policy("bucket", "private")
        mock.delete_bucket_policy.assert_called_once_with("bucket")
        mock.set_bucket_policy.assert_not_called()


def test_set_bucket_policy_public_read() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        client = UWS3("key", "secret")
        client.set_bucket_policy("bucket", "public-read")

        policy_json = mock.set_bucket_policy.call_args[0][1]
        policy = json.loads(policy_json)
        assert len(policy["Statement"]) == 2
        actions = policy["Statement"][1]["Action"]
        assert actions == "s3:GetObject"


def test_set_bucket_policy_public_readwrite() -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        client = UWS3("key", "secret")
        client.set_bucket_policy("bucket", "public-readwrite")

        policy_json = mock.set_bucket_policy.call_args[0][1]
        policy = json.loads(policy_json)
        assert len(policy["Statement"]) == 2
        actions = policy["Statement"][1]["Action"]
        assert "s3:PutObject" in actions
        assert "s3:DeleteObject" in actions
        assert "s3:GetObject" in actions


def test_set_bucket_policy_invalid_raises() -> None:
    with patch("uw_s3.Minio"):
        client = UWS3("key", "secret")
        with pytest.raises(ValueError, match="Unknown permission"):
            client.set_bucket_policy("bucket", "bogus")


def test_upload_file(tmp_path) -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        f = tmp_path / "data.bin"
        f.write_bytes(b"x")

        client = UWS3("key", "secret")
        client.upload_file("bucket", "data.bin", f)
        mock.fput_object.assert_called_once_with("bucket", "data.bin", str(f))


def test_download_file(tmp_path) -> None:
    with patch("uw_s3.Minio") as MockMinio:
        mock = MockMinio.return_value
        dest = tmp_path / "out.bin"

        client = UWS3("key", "secret")
        client.download_file("bucket", "out.bin", dest)
        mock.fget_object.assert_called_once_with("bucket", "out.bin", str(dest))
