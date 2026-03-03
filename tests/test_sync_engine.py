"""Tests for the sync engine."""

from pathlib import Path
from unittest.mock import MagicMock

from uw_s3.sync.engine import SyncEngine, SyncAction
from uw_s3.sync.models import SyncMap


def _mock_client(remote_objects: list[tuple[str, int]]) -> MagicMock:
    """Create a mock UWS3 client with given remote objects."""
    client = MagicMock()
    client.list_objects_with_size.return_value = remote_objects
    return client


def test_status_push_detects_missing_on_remote(tmp_path: Path) -> None:
    local_file = tmp_path / "hello.txt"
    local_file.write_text("hello")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="test-bucket")
    engine = SyncEngine(_mock_client([]), mapping)

    actions = engine.status_push()
    assert len(actions) == 1
    assert actions[0].relative_path == "hello.txt"
    assert actions[0].direction == "push"
    assert actions[0].reason == "missing on S3"


def test_status_push_detects_size_diff(tmp_path: Path) -> None:
    local_file = tmp_path / "data.bin"
    local_file.write_bytes(b"abcde")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="test-bucket")
    engine = SyncEngine(_mock_client([("data.bin", 999)]), mapping)

    actions = engine.status_push()
    assert len(actions) == 1
    assert actions[0].reason == "size differs"


def test_status_push_skips_synced_files(tmp_path: Path) -> None:
    local_file = tmp_path / "synced.txt"
    local_file.write_bytes(b"12345")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="test-bucket")
    engine = SyncEngine(_mock_client([("synced.txt", 5)]), mapping)

    actions = engine.status_push()
    assert actions == []


def test_status_pull_detects_missing_locally(tmp_path: Path) -> None:
    mapping = SyncMap(local_dir=str(tmp_path), bucket="test-bucket")
    engine = SyncEngine(_mock_client([("remote.txt", 100)]), mapping)

    actions = engine.status_pull()
    assert len(actions) == 1
    assert actions[0].relative_path == "remote.txt"
    assert actions[0].direction == "pull"
    assert actions[0].reason == "missing locally"


def test_status_pull_detects_size_diff(tmp_path: Path) -> None:
    local_file = tmp_path / "data.bin"
    local_file.write_bytes(b"ab")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="test-bucket")
    engine = SyncEngine(_mock_client([("data.bin", 999)]), mapping)

    actions = engine.status_pull()
    assert len(actions) == 1
    assert actions[0].reason == "size differs"


def test_status_pull_skips_synced_files(tmp_path: Path) -> None:
    local_file = tmp_path / "synced.txt"
    local_file.write_bytes(b"12345")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="test-bucket")
    engine = SyncEngine(_mock_client([("synced.txt", 5)]), mapping)

    actions = engine.status_pull()
    assert actions == []


def test_push_calls_upload(tmp_path: Path) -> None:
    local_file = tmp_path / "new.txt"
    local_file.write_text("data")

    client = _mock_client([])
    mapping = SyncMap(local_dir=str(tmp_path), bucket="test-bucket")
    engine = SyncEngine(client, mapping)

    actions = engine.push()
    assert len(actions) == 1
    client.upload_file.assert_called_once_with("test-bucket", "new.txt", local_file)


def test_pull_calls_download(tmp_path: Path) -> None:
    client = _mock_client([("remote.txt", 42)])
    mapping = SyncMap(local_dir=str(tmp_path), bucket="test-bucket")
    engine = SyncEngine(client, mapping)

    actions = engine.pull()
    assert len(actions) == 1
    client.download_file.assert_called_once_with(
        "test-bucket", "remote.txt", tmp_path / "remote.txt"
    )


def test_push_with_prefix(tmp_path: Path) -> None:
    local_file = tmp_path / "file.txt"
    local_file.write_text("x")

    client = _mock_client([])
    mapping = SyncMap(local_dir=str(tmp_path), bucket="b", prefix="sub/dir")
    engine = SyncEngine(client, mapping)

    engine.push()
    client.upload_file.assert_called_once_with("b", "sub/dir/file.txt", local_file)


def test_push_callback(tmp_path: Path) -> None:
    local_file = tmp_path / "cb.txt"
    local_file.write_text("x")

    client = _mock_client([])
    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(client, mapping)

    called: list[SyncAction] = []
    engine.push(callback=called.append)
    assert len(called) == 1
    assert called[0].relative_path == "cb.txt"


def test_nested_files(tmp_path: Path) -> None:
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    (sub / "deep.txt").write_text("deep")

    client = _mock_client([])
    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(client, mapping)

    actions = engine.status_push()
    assert len(actions) == 1
    assert actions[0].relative_path == "a/b/deep.txt"


def test_pull_creates_nested_dirs(tmp_path: Path) -> None:
    client = _mock_client([("x/y/deep.txt", 10)])
    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(client, mapping)

    engine.pull()
    client.download_file.assert_called_once_with(
        "b", "x/y/deep.txt", tmp_path / "x" / "y" / "deep.txt"
    )
    assert (tmp_path / "x" / "y").is_dir()


def test_status_push_empty_local_dir(tmp_path: Path) -> None:
    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(_mock_client([("remote.txt", 5)]), mapping)

    assert engine.status_push() == []


def test_pull_callback(tmp_path: Path) -> None:
    client = _mock_client([("file.txt", 7)])
    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(client, mapping)

    called: list[SyncAction] = []
    engine.pull(callback=called.append)
    assert len(called) == 1
    assert called[0].relative_path == "file.txt"
    assert called[0].direction == "pull"


def test_pull_with_prefix(tmp_path: Path) -> None:
    client = _mock_client([("data/file.txt", 3)])
    mapping = SyncMap(local_dir=str(tmp_path), bucket="b", prefix="data")
    engine = SyncEngine(client, mapping)

    engine.pull()
    client.download_file.assert_called_once_with(
        "b", "data/file.txt", tmp_path / "file.txt"
    )
