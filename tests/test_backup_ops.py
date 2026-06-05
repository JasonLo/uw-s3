"""Tests for the programmatic backup/restore operations."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from uw_s3.backup_ops import parse_s3_uri, run_backup, run_restore


def test_parse_s3_uri_with_key():
    assert parse_s3_uri("s3://mybucket/docs/report.pdf") == (
        "mybucket",
        "docs/report.pdf",
    )


def test_parse_s3_uri_bucket_only():
    assert parse_s3_uri("s3://mybucket") == ("mybucket", "")


def test_parse_s3_uri_rejects_non_s3_scheme():
    with pytest.raises(ValueError):
        parse_s3_uri("/local/path")


def test_parse_s3_uri_rejects_bad_bucket_name():
    with pytest.raises(ValueError):
        parse_s3_uri("s3://Invalid_Bucket/key")


def test_run_backup_folder_incremental(tmp_path: Path):
    (tmp_path / "a.txt").write_text("aaa")  # 3 bytes, already in sync
    (tmp_path / "b.txt").write_text("bb")  # 2 bytes, new
    client = MagicMock()
    client.iter_objects_with_size.return_value = iter([("a.txt", 3)])

    result = run_backup(client, tmp_path, "bucket", "", endpoint="campus.s3.wisc.edu")

    assert result.transferred == 1
    assert result.skipped == 1
    assert result.bytes == 2
    assert result.paths == ["b.txt"]
    client.upload_file.assert_called_once_with("bucket", "b.txt", tmp_path / "b.txt")


def test_run_backup_folder_dry_run_uploads_nothing(tmp_path: Path):
    (tmp_path / "b.txt").write_text("bb")
    client = MagicMock()
    client.iter_objects_with_size.return_value = iter([])

    result = run_backup(client, tmp_path, "bucket", "", dry_run=True)

    assert result.transferred == 1
    assert result.dry_run is True
    client.upload_file.assert_not_called()


def test_run_backup_single_file(tmp_path: Path):
    f = tmp_path / "report.pdf"
    f.write_text("hello")
    client = MagicMock()

    result = run_backup(client, f, "bucket", "docs/report.pdf")

    assert result.transferred == 1
    assert result.bytes == 5
    assert result.paths == ["docs/report.pdf"]
    client.upload_file.assert_called_once_with("bucket", "docs/report.pdf", f)


def test_run_backup_missing_local_path(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        run_backup(MagicMock(), tmp_path / "nope", "bucket", "k")


def test_run_restore_single_object(tmp_path: Path):
    client = MagicMock()
    client.list_objects_with_size.return_value = [("docs/report.pdf", 10)]
    dest = tmp_path / "out.pdf"

    result = run_restore(client, "bucket", "docs/report.pdf", dest)

    assert result.transferred == 1
    assert result.bytes == 10
    client.download_file.assert_called_once_with("bucket", "docs/report.pdf", dest)


def test_run_restore_single_object_into_existing_dir(tmp_path: Path):
    client = MagicMock()
    client.list_objects_with_size.return_value = [("docs/report.pdf", 10)]

    result = run_restore(client, "bucket", "docs/report.pdf", tmp_path)

    expected = tmp_path / "report.pdf"
    client.download_file.assert_called_once_with("bucket", "docs/report.pdf", expected)
    assert result.paths == [str(expected)]


def test_run_restore_prefix(tmp_path: Path):
    client = MagicMock()
    client.list_objects_with_size.return_value = [("snap/a.txt", 3), ("snap/b.txt", 2)]
    client.iter_objects_with_size.return_value = iter(
        [("snap/a.txt", 3), ("snap/b.txt", 2)]
    )

    result = run_restore(client, "bucket", "snap", tmp_path)

    assert result.transferred == 2
    assert result.bytes == 5
    assert client.download_file.call_count == 2


def test_run_restore_prefix_dry_run_downloads_nothing(tmp_path: Path):
    client = MagicMock()
    client.list_objects_with_size.return_value = [("snap/a.txt", 3)]
    client.iter_objects_with_size.return_value = iter([("snap/a.txt", 3)])

    result = run_restore(client, "bucket", "snap", tmp_path, dry_run=True)

    assert result.transferred == 1
    assert result.dry_run is True
    client.download_file.assert_not_called()


def test_run_restore_no_objects(tmp_path: Path):
    client = MagicMock()
    client.list_objects_with_size.return_value = []
    with pytest.raises(FileNotFoundError):
        run_restore(client, "bucket", "missing", tmp_path)
