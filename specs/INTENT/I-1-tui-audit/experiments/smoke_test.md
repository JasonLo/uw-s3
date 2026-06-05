# TUI Audit — Manual Smoke Test

Pre-merge checklist for the Textual best-practice remediation branch. Every section MUST pass on both endpoints (`campus`, `web`) before merge.

Launch with `uv run uws3`. Open the Textual dev console in a second terminal (`uv run textual console`) for the full pass — no traceback may appear.

## Endpoint switch
- [x] Launch app — main menu renders; last-used endpoint restored from `~/.config/uw-s3/preferences.json`.
- [x] Toggle endpoint `campus` ↔ `web` — bucket list reloads without restart.
- [x] Restart app — saved endpoint and last bucket are restored.

## Bucket management
- [x] List buckets — table renders within ~1 render frame after the worker returns.
- [x] Create a bucket with a valid name — it appears in the list.
- [x] Reject an invalid bucket name — validation error shown, no S3 call made.
- [x] Set bucket permissions — change visible after refresh.
- [x] Delete an empty bucket — it disappears from the list.

## File manager
- [x] Open a bucket — object list renders; subdirectory navigation works.
- [x] Upload a single file — it appears in the listing.
- [x] Download a single file — file is written to the chosen path.
- [x] Open a sub-prefix and navigate back — breadcrumb / state correct.

## Sync
- [x] Configure a sync map (local dir ↔ bucket) — saved to `~/.config/uw-s3/sync.json`.
- [x] Preview push — diff summary appears; no objects modified.
- [x] Execute push — progress callback updates UI continuously; objects uploaded.
- [x] Preview pull — diff summary appears; no local files modified.
- [x] Execute pull — local files written; progress callback updates UI continuously.

## Mount
- [ ] Mount a bucket — Python `s3fs` FUSE handler thread starts; mount point lists top-level files within 3 s.
- [ ] Unmount — `fusermount -u` completes within 5 s; FUSE handler thread exits; mount point listing is empty / file manager `DirectoryTree` reloads.
- [ ] Quit app while mounted — `UWS3App.on_unmount()` cleanup runs without blocking the event loop; `pgrep -x s3fs` and `pgrep -x rclone` both return empty.

## Responsiveness
- [x] During any long-running worker (sync, large list), Escape and Tab keys respond and the footer updates within one render frame.
- [x] No traceback appears in the Textual dev console across the full pass.

## Sign-off
- Tester: ____________________
- Date: ____________________
- Endpoints exercised: [ ] campus [ ] web
