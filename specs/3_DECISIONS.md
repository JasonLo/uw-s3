# Decisions Log

Append-only log of non-trivial decisions. Each entry: `D-NNNN: Decided X because Y (YYYY-MM-DD).`

- **D-0001:** Decided to keep per-screen inline `CSS = """..."""` blocks instead of an external `CSS_PATH` `.tcss` file because the 7 blocks have no duplication and `textual run --dev` live-edit is unused (2026-05-22). [intent: IT-1]
- **D-0002:** Decided to keep `call_from_thread` via `S3Screen.ui()` for worker→UI updates instead of `post_message` because Constitution §Architecture principle 4 already mandates it (2026-05-22). [intent: IT-1]
- **D-0003:** Decided to replace rclone with Python `s3fs` (in-process via `fsspec.fuse`) rather than `s3fs-fuse` (external binary) because rclone reproduced its known brittleness on the first run (60s of `errno=5` on `os.listdir`, orphan PID + stale `fuse.rclone` mount on the *normal* unmount path), `s3fs-fuse` carries the same persistent-`ENOTCONN`-on-crash + orphan-PID failure mode as rclone, and Python `s3fs` cannot leak an orphan helper because there is no helper binary (FUSE handler lives in the python process; kernel reaps the mount when the process dies); freshness ~50ms vs rclone never, mount latency 0.27s vs target ≤3s — full data in `specs/2_INTENT/IT-2-s3fs-migration/experiments/results.md` (2026-05-22). [intent: IT-2]
