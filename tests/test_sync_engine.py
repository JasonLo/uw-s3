"""Tests for the sync engine."""

from pathlib import Path
from unittest.mock import MagicMock

from uw_s3.sync.engine import SyncEngine, SyncAction
from uw_s3.sync.models import SyncMap


def _mock_client(remote_objects: list[tuple[str, int]]) -> MagicMock:
    """Create a mock UWS3 client with given remote objects."""
    client = MagicMock()
    client.iter_objects_with_size.side_effect = lambda *a, **kw: iter(remote_objects)
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


def test_summary_push_counts_in_sync_and_new(tmp_path: Path) -> None:
    (tmp_path / "match.txt").write_bytes(b"abc")
    (tmp_path / "new.txt").write_bytes(b"xyz")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(_mock_client([("match.txt", 3)]), mapping)

    summary = engine.summary_push()
    assert summary.in_sync == 1
    assert summary.new == 1
    assert summary.size_differs == 0
    assert summary.to_transfer == 1
    assert summary.actions[0].relative_path == "new.txt"


def test_summary_push_counts_size_differs(tmp_path: Path) -> None:
    (tmp_path / "data.bin").write_bytes(b"abcde")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(_mock_client([("data.bin", 999)]), mapping)

    summary = engine.summary_push()
    assert summary.in_sync == 0
    assert summary.new == 0
    assert summary.size_differs == 1
    assert summary.to_transfer == 1


def test_summary_pull_counts_in_sync(tmp_path: Path) -> None:
    (tmp_path / "match.txt").write_bytes(b"abc")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(
        _mock_client([("match.txt", 3), ("remote-only.txt", 10)]), mapping
    )

    summary = engine.summary_pull()
    assert summary.in_sync == 1
    assert summary.new == 1
    assert summary.size_differs == 0
    assert summary.to_transfer == 1
    assert summary.actions[0].relative_path == "remote-only.txt"


def test_summary_push_invokes_progress_phases(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("bb")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(_mock_client([("a.txt", 1)]), mapping)

    calls: list[tuple[str, int]] = []
    engine.summary_push(progress=lambda phase, count: calls.append((phase, count)))

    phases_seen = [phase for phase, _ in calls]
    assert "local" in phases_seen
    assert "remote" in phases_seen
    assert "compare" in phases_seen
    assert phases_seen.index("local") < phases_seen.index("remote")
    assert phases_seen.index("remote") < phases_seen.index("compare")


def test_progress_cancellation_propagates(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("x")

    mapping = SyncMap(local_dir=str(tmp_path), bucket="b")
    engine = SyncEngine(_mock_client([]), mapping)

    class _Cancel(Exception):
        pass

    def progress(phase: str, count: int) -> None:
        raise _Cancel

    try:
        engine.summary_push(progress=progress)
    except _Cancel:
        return
    raise AssertionError("expected _Cancel to propagate from progress callback")
