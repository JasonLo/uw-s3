# Intent Doc: S3 mount backend — replace rclone with s3fs

- **Author:** clo36@wisc.edu
- **Status:** Draft
- **Last updated:** 2026-05-22

## Problem

The current rclone FUSE mount is brittle along three axes that blocked the previous intent's Mount-flow sign-off: (1) **process lifecycle** — orphan `rclone` survives app exit, `on_unmount` stalls the event loop, SIGTERM→SIGKILL teardown races; (2) **setup friction** — FUSE permissions, mountpoint creation, kernel-module variance across platforms; (3) **listing behavior** — empty/stale directory listings, slow first-list, files from outside clients don't appear. We want to prototype `s3fs-fuse` (external binary) and `s3fs` (Python fsspec library, in-process), pick the better fit, then remove rclone entirely.

## Outcome

- **WHEN** the user presses Mount on a bucket, **THE SYSTEM SHALL** surface its top-level contents at the chosen mountpoint within 3 seconds.
- **WHEN** the user presses Unmount, **THE SYSTEM SHALL** release the mountpoint within 5 seconds and leave no orphan mount helpers (`pgrep -f s3fs` and `pgrep -f rclone` both return empty).
- **WHEN** the app exits while a mount is active, **THE SYSTEM SHALL** clean up all mount processes within 5 seconds without blocking the Textual event loop (Constitution §4 still binds).
- **WHEN** the chosen backend lands on `main`, **THE SYSTEM SHALL** contain no `rclone.py`, no `RcloneMount`, no `RCLONE_CONFIG_UWS3_*` env wiring, and no reference to `rclone` in source or `pyproject.toml`.
- **WHEN** the new backend is in place, **THE SYSTEM SHALL** have every Mount checkbox in `experiments/tui_audit/smoke_test.md` verified on both `campus` and `web` endpoints, with the Sign-off block filled in.

## Non-Goals

- NOT adding mount features beyond 1:1 rclone parity (no read-write tiering, no shared mounts, no auto-remount on connection drop).
- NOT changing the credentials model — still env / `.env` only, per Constitution §9.
- NOT touching the file-manager browse path or sync engine — they remain S3-API based, independent of mount.
- NOT keeping rclone as a fallback after the migration ships.
- NOT supporting Windows-native mounts; WSL2 + Linux + macOS only.
- NOT bundling `s3fs-fuse` as a Python dep — it stays an external binary on PATH (mirroring how rclone was treated).

## Constraints

- **Constitution §4** — mount lifecycle calls from the TUI MUST run on `@work(thread=True)` with UI updates via `call_from_thread()`.
- **Constitution §8 conflict** — §8 names rclone explicitly. Full removal makes §8 moot post-merge; adopting Python `s3fs` would also violate §8's spirit ("mount helpers stay external, not Python deps"). Invoke `/ls-constitution` to generalize §8 before the chosen backend merges.
- **Constitution §9** — credentials remain env-only; neither backend may write creds to disk.
- Both s3fs flavors MUST be prototyped against `experiments/tui_audit/smoke_test.md#Mount` on both endpoints; the backend choice is data-driven from that exercise and logged in `specs/3_DECISIONS.md`.
- Target platforms: Linux (incl. WSL2 with fuse3), macOS optional. No Windows-native FUSE.
- `s3fs-fuse` and Python `s3fs` MUST both honor the existing `S3_ENDPOINT` switch (`campus` ↔ `web`).

## Change Log

- **2026-05-22** — Initial draft. Picks up the Mount-flow follow-up deferred by the previous (Complete) Textual TUI audit intent.
