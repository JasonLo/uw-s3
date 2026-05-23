# s3fs Backend Evaluation

This folder backs the decision called for in `specs/2_INTENT.md`: which
`s3fs` flavor replaces rclone as the mount backend.

Two candidates, prototyped side-by-side:

| Backend | Deployment | Script |
| --- | --- | --- |
| `s3fs-fuse` (external C binary on `PATH`) | mirrors how rclone was treated | `try_s3fs_fuse.sh` |
| Python `s3fs` (fsspec library, in-process) | adds a Python dep, no external binary | `try_s3fs_python.py` |

## Prerequisites

- A UW-S3 bucket you can list (use the same one used in `experiments/tui_audit/smoke_test.md`).
- `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` in your shell environment (do not write them to disk — Constitution §9).
- For `try_s3fs_fuse.sh`: the `s3fs` binary on `PATH`. Install with `sudo apt install s3fs` (Debian/Ubuntu), `brew install s3fs` (macOS), or build from https://github.com/s3fs-fuse/s3fs-fuse.
- For `try_s3fs_python.py`: install the deps into the project venv: `uv pip install s3fs 'fsspec[fuse]' fusepy`. These will NOT be added to `pyproject.toml` until/unless this backend wins.
- Linux/WSL2: `fuse3` and `/dev/fuse` accessible to your user.

## Running

Each script takes a bucket name and an endpoint key (`campus` or `web`):

```bash
./try_s3fs_fuse.sh <bucket> campus
./try_s3fs_fuse.sh <bucket> web

uv run python try_s3fs_python.py <bucket> campus
uv run python try_s3fs_python.py <bucket> web
```

Both scripts:

1. Allocate a temp mount point.
2. Mount the bucket, polling until the mount comes up (or 10s timeout).
3. Print the mount-establish latency.
4. List the top-level directory entries.
5. Stay running until you press Ctrl-C, then unmount cleanly.

While the mount is up, exercise it from a second terminal:

```bash
# Repeat-list (cache freshness)
ls $MNT
# Upload from another client (e.g. mc, the TUI itself) and confirm it appears
ls $MNT
# Force a failure: kill -9 the mount process and see what the mount point looks like
```

After Ctrl-C, confirm no orphan helpers remain:

```bash
pgrep -fa s3fs
pgrep -fa rclone   # should already be empty
```

## Recording results

Fill `results.md` as you go. Both endpoints (`campus` and `web`) must
be exercised for each backend before the decision in
`specs/3_DECISIONS.md` can be written.
