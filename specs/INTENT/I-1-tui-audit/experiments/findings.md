# TUI Audit — Findings

Audit of `src/uw_s3/tui/` against the official Textual documentation at https://textual.textualize.io/ (textual >= 4.0.0 pinned in `pyproject.toml`).

- **Date:** 2026-05-22
- **Auditor:** Claude (Opus 4.7) for clo36@wisc.edu
- **Method:** Targeted reference pass against the 8 doc pages that match patterns in this codebase (Workers, Screens, App, Widgets, CSS, Events, Testing, Devtools), then file-by-file walkthrough of `app.py`, `screens/base.py`, `screens/main_menu.py`, `screens/file_manager.py`, `screens/bucket_management.py`, `screens/mount.py`, `screens/confirm.py`, `screens/input_dialog.py`, and `tests/test_tui.py`.

Severity definitions (from the I-1 intent doc, `../intent.md`):
- `blocker` — correctness/safety bug that must be fixed before merge.
- `major` — clear deviation from prescriptive docs guidance with user-visible impact.
- `minor` — best-practice nit or maintainability improvement.

## Summary

| Severity | Initial | After remediation |
|----------|--------:|------------------:|
| blocker  | 0       | 0                 |
| major    | 3       | 0 (all fixed)     |
| minor    | 8       | 0 (6 fixed, 2 accepted via DECISIONS) |
| **Total**| **11**  | **0 open**        |

**Status:** Outcomes 1–3 of the I-1 intent (`../intent.md`) satisfied as of 2026-05-22. Outcome 4 (smoke test on both endpoints) is pending the user-driven walkthrough of `./smoke_test.md`.

---

## Major findings

### [major] M1 — Sync cancellation bypasses the worker-state pattern
- **File:** `src/uw_s3/tui/screens/file_manager.py:138`, `:144`, `:455-468`, `:514-517`
- **What we do:** A screen-level `threading.Event` (`self._sync_cancelled`) is used to signal cancellation, checked inside `_make_scan_progress_callback` and the `on_file` callback. The base class' `action_pop_screen` (`screens/base.py:53`) calls `self.workers.cancel_all()` on screen pop, but those workers never check `worker.is_cancelled`, so popping the file-manager screen mid-sync leaves the upload/download loop running until the next manual cancel.
- **What docs say:** Thread workers must obtain their worker handle and inspect `worker.is_cancelled` before continuing or updating the UI: "Unlike async workers, threaded workers can't be cancelled by Textual… you will need to check the value of `Worker.is_cancelled` periodically."
- **Citation:** https://textual.textualize.io/guide/workers/#thread-workers
- **Remediation sketch:** In `_run_sync` / `_run_preview`, obtain `worker = get_current_worker()` and check `worker.is_cancelled` in the scan-progress callback and the per-file callback (alongside or instead of the threading.Event). Keep the user-pressed Cancel button as an additional path but route it through `worker.cancel()` so a single cancellation surface drives both code paths.

### [major] M2 — `UWS3App.on_unmount` runs blocking subprocess teardown on the event loop
- **File:** `src/uw_s3/tui/app.py:53-63`
- **What we do:** `on_unmount` calls `cleanup_mounts()`, which iterates `active_mounts` and invokes `rm.unmount()` synchronously. Each `RcloneMount.unmount()` issues SIGTERM, waits, and may fall through to SIGKILL — blocking the event loop for seconds-per-mount during app exit. The Outcome 4 manual checkbox "Quit app while mounted — `on_unmount` cleanup runs; `pgrep rclone` returns no orphan" depends on this path completing, but the user sees a frozen terminal until it does.
- **What docs say:** "Long-running operations should be offloaded to background tasks… to maintain UI responsiveness. Slow handlers prevent the widget from processing new messages." Event handlers — including lifecycle handlers — should not block.
- **Citation:** https://textual.textualize.io/guide/events/#message-handlers (async handlers / "slow handlers" warning)
- **Remediation sketch:** Make `on_unmount` async and `await` an `asyncio.to_thread(self.cleanup_mounts)`, OR launch the teardown via `@work(thread=True)` and `await` its completion before returning. Either path keeps the event loop responsive while the rclone processes are reaped.

### [major] M3 — Thread workers update widgets without checking `worker.is_cancelled`
- **File:** `src/uw_s3/tui/screens/file_manager.py:206-266`, `:650-666`, `:713-744`; `src/uw_s3/tui/screens/bucket_management.py:133-145`, `:163-186`, `:202-214`, `:216-240`; `src/uw_s3/tui/screens/mount.py:132-142`, `:163-184`, `:206-245`, `:247-271`
- **What we do:** Every `@work(thread=True)` method writes back to widgets via `self.ui(...)` (i.e., `call_from_thread`) without first checking whether the worker (or its owning screen) is still alive. When `S3Screen.action_pop_screen` cancels workers (`screens/base.py:53`), Textual marks them cancelled but the threads keep running and continue to push updates into the now-unmounted widget tree. The Pilot test suite happens to not exercise this path, so it has been silently shipping.
- **What docs say:** Thread workers must "manually check `worker.is_cancelled` before updating the UI from a thread" and "must avoid calling methods on your UI directly from a threaded worker"; the recommended pattern uses `worker = get_current_worker()` then `if not worker.is_cancelled: self.call_from_thread(...)`.
- **Citation:** https://textual.textualize.io/guide/workers/#thread-workers
- **Remediation sketch:** Update `S3Screen.ui()` (`screens/base.py:49`) to accept the current worker and short-circuit when cancelled, OR introduce a `ui_if_alive` helper that callers in each worker invoke after `worker = get_current_worker()`. Apply to every `@work(thread=True)` method enumerated above. A single helper keeps the call-site change mechanical.

---

## Minor findings

### [minor] m1 — Inline `CSS = """..."""` instead of external `CSS_PATH`
- **File:** `screens/main_menu.py:36`, `screens/file_manager.py:78`, `screens/bucket_management.py:31` & `:91`, `screens/mount.py:46`, `screens/confirm.py:13`, `screens/input_dialog.py:14` (7 inline blocks across screens/modals).
- **What we do:** All app/screen styling lives in inline `CSS = """..."""` class variables. Total ~135 lines of CSS spread across files.
- **What docs say:** CSS_PATH "separates how your app _looks_ from how it _works_… and enables live editing with `textual run my_app.py --dev`." External `.tcss` files are recommended for app-wide styling.
- **Citation:** https://textual.textualize.io/guide/CSS/ (CSS_PATH section)
- **Remediation sketch:** Promote app-level rules to `src/uw_s3/tui/uw_s3.tcss` referenced via `UWS3App.CSS_PATH`. Keep widget-scoped styling in `DEFAULT_CSS` for reusable widgets like `EndpointBar` (already correct). Per-screen styles stay inline if migrating is churn-y — accept that as the project's choice via `specs/DECISIONS.md` if desired.

### [minor] m2 — Workers lack `exclusive=True` / `group=` and can stack on key spam
- **File:** `screens/file_manager.py:206` (`_load_buckets`), `:223` (`_load_objects`), `:650` (`_do_delete`), `:713` (`_do_rename`); `screens/mount.py:132` (`_load_buckets`).
- **What we do:** These workers are declared `@work(thread=True)` with no `exclusive` flag or `group`. Pressing Refresh twice in quick succession (or rapid-fire `r`) queues parallel `list_buckets` / `list_objects` requests.
- **What docs say:** "The `exclusive` flag tells Textual to cancel all previous workers before starting the new one… prevents race conditions where responses arrive out-of-order."
- **Citation:** https://textual.textualize.io/guide/workers/#work-decorator
- **Remediation sketch:** Add `exclusive=True, group="load"` (matching `bucket_management.py`'s convention) to the list/refresh workers; add `exclusive=True, group="mutate"` to `_do_delete` / `_do_rename` if serializing mutations is desired.

### [minor] m3 — `ConfirmScreen` has no Escape binding
- **File:** `src/uw_s3/tui/screens/confirm.py:10`
- **What we do:** `ConfirmScreen` exposes `Yes` / `Cancel` buttons but no `Binding("escape", ...)`. Sibling modals `InputScreen` (`input_dialog.py:29`) and `CreateBucketScreen` (`bucket_management.py:48`) both bind Escape → cancel.
- **What docs say:** Modal screens should let users dismiss them; the screens guide demonstrates `Binding("escape", "app.pop_screen", "Pop screen")` on dialog examples.
- **Citation:** https://textual.textualize.io/guide/screens/#modal-screens
- **Remediation sketch:** Add `BINDINGS = [Binding("escape", "no", "Cancel")]` and an `action_no` that calls `self.dismiss(False)`.

### [minor] m4 — Multiple `call_from_thread` calls in one worker could be a single `post_message`
- **File:** `screens/file_manager.py:207-218` (5 sequential `self.ui(...)` calls in `_load_buckets`), and similar patterns in `_load_objects` and the sync overlay update path.
- **What we do:** Workers issue 3–5 consecutive `call_from_thread` invocations to update one logical UI state.
- **What docs say:** "If your worker needs to make multiple updates to the UI, it is a good idea to send custom messages and have the widget update itself."
- **Citation:** https://textual.textualize.io/guide/workers/#posting-messages
- **Remediation sketch:** Define a few `Message` subclasses (e.g., `BucketsLoaded`, `ObjectsLoaded`, `ScanProgressed`) and `post_message` them from workers; have the screen update its widgets in the handler. Lower priority than M1–M3.

### [minor] m5 — `bucket_management._confirm_force_delete` pushes a modal from a worker via `call_from_thread`
- **File:** `src/uw_s3/tui/screens/bucket_management.py:188-200`
- **What we do:** The thread worker `_delete_selected` calls `self._confirm_force_delete(...)`, which marshals `self.app.push_screen(ConfirmScreen(...), on_confirm)` through `self.ui(...)`. Pushing a screen via `call_from_thread` works but reads as accidentally cross-cutting.
- **What docs say:** Modal screens "manipulating app state directly… reduces reusability." The cleaner pattern is to post a custom message and have the main-thread handler decide whether to push a screen.
- **Citation:** https://textual.textualize.io/guide/screens/#returning-data-from-screens (callback / dismiss pattern)
- **Remediation sketch:** Post a `BucketNotEmpty(bucket_name, row_key)` message from the worker; the screen's `on_bucket_not_empty` handler pushes the `ConfirmScreen`.

### [minor] m6 — `MainMenuScreen` actions push screens without guards
- **File:** `src/uw_s3/tui/screens/main_menu.py:97-113` (`action_file_manager`, `action_bucket_management`, `action_mount_bucket`)
- **What we do:** Each action calls `self.app.push_screen(...)` unconditionally. Spamming `1`, `1`, `1` quickly will stack three `BucketManagementScreen` instances on the stack.
- **What docs say:** Listed anti-pattern: "Calling `push_screen()` without guards — creates duplicate screens on repeated key presses."
- **Citation:** https://textual.textualize.io/guide/screens/ (anti-patterns section)
- **Remediation sketch:** Guard with `if not isinstance(self.app.screen, BucketManagementScreen): self.app.push_screen(...)`, or wrap in a small helper that checks `self.app.screen_stack` for the target class.

### [minor] m7 — Pilot test coverage gaps on file-manager, mount, and worker paths
- **File:** `tests/test_tui.py` (130 lines, 10 tests)
- **What we do:** Tests cover main menu, endpoint toggle, escape navigation, confirm modal, and on_unmount cleanup. There are no Pilot tests for `FileManagerScreen` (bucket select → list objects), `MountScreen`, sync preview/execute, or any thread-worker scenario.
- **What docs say:** Pilot supports `pause()` and async test conventions for exactly these flows; testing screens that push other screens is an explicit Pilot use case.
- **Citation:** https://textual.textualize.io/guide/testing/
- **Remediation sketch:** Add Pilot tests for: (a) pressing `2` from main menu opens `FileManagerScreen` and `_load_buckets` populates `#bucket-select`; (b) `ConfirmScreen` cancellation via Escape (after m3 is fixed); (c) a mocked sync that exercises the cancellation path (after M1 is fixed). Useful as regression tests for the major fixes.

### [minor] m8 — Test uses private attribute `app._exit`
- **File:** `tests/test_tui.py:45`
- **What we do:** `test_quit_key` asserts `app.return_code is not None or app._exit`. `_exit` is a Textual internal.
- **What docs say:** The testing guide shows `app.return_code` and `app.exit_code` as the public surfaces.
- **Citation:** https://textual.textualize.io/guide/testing/
- **Remediation sketch:** Replace `app._exit` with `app.return_code is not None` (the leading clause already covers this) or assert on `app.is_running is False` after `pilot.press("q")` + `pilot.pause()`.

---

## What the audit found to be correct

Recording these so we don't regress them:

- `compose()` methods are pure and called once per screen; no DOM mutation outside `compose()` or event handlers. (Matches https://textual.textualize.io/guide/widgets/.)
- `EndpointBar` uses `DEFAULT_CSS` — correct pattern for a reusable, self-contained widget. (https://textual.textualize.io/guide/CSS/.)
- Modal screens use `ModalScreen[ReturnType]` typing and `dismiss(value)` plus `push_screen(..., callback)` — the idiomatic data-flow pattern. (https://textual.textualize.io/guide/screens/#returning-data-from-screens.)
- All blocking S3 / filesystem / subprocess work originates in `@work(thread=True)` (with the on_unmount exception flagged as M2). Outcome 3 of the intent is structurally satisfied — the M3 finding is about *cancellation safety within* those workers, not their absence.
- `BucketManagementScreen` consistently uses `exclusive=True` + `group=` on its workers (`load`, `delete`, `create`) — the rest of the codebase should match this convention.
- Pilot harness (`app.run_test()`) is already the project's chosen test backend.

---

## Remediation log (2026-05-22)

| ID | Disposition | Where it landed |
|----|-------------|-----------------|
| M1 | Fixed       | `screens/file_manager.py` — `threading.Event` removed; `worker.is_cancelled` drives both scan and per-file callbacks; Cancel button now calls `self.workers.cancel_group(self, "sync")`; sync actions tagged `group="sync"`. |
| M2 | Fixed       | `app.py` — `on_unmount` is async and offloads `cleanup_mounts()` via `asyncio.to_thread`. |
| M3 | Fixed       | `screens/base.py` — `S3Screen.ui()` now fetches `get_current_worker()` and no-ops when the worker is cancelled (defensive `NoActiveWorker` fallback runs `fn` directly on the main thread). Single helper change covers every `@work(thread=True)` call site. |
| m1 | Accepted    | `specs/DECISIONS.md` D-0001 — inline `CSS = """..."""` retained. |
| m2 | Fixed       | `file_manager.py` (`_load_buckets`, `_load_objects`, `_do_delete`, `_do_rename`) and `mount.py` (`_load_buckets`) now declare `exclusive=True` with appropriate `group=` (`load` / `mutate`). |
| m3 | Fixed       | `screens/confirm.py` — `Binding("escape", "no", "Cancel")` added; `_no` renamed to `action_no`. |
| m4 | Accepted    | `specs/DECISIONS.md` D-0002 — `call_from_thread` retained per Constitution §Architecture principle 4. |
| m5 | Fixed       | `bucket_management.py` — `BucketNotEmpty` Message defined and posted from worker; main-thread `_on_bucket_not_empty` pushes the confirm modal. |
| m6 | Fixed       | `main_menu.py` — actions route through `_push_unique()` that guards on `isinstance(self.app.screen, type(screen))`. |
| m7 | Fixed       | `tests/test_tui.py` — added `test_confirm_screen_escape_dismisses_as_false` and `test_navigate_to_file_manager`. |
| m8 | Fixed       | `tests/test_tui.py:test_quit_key` — `app._exit` replaced with `not app.is_running`. |

Verification at remediation time:
- `uv run ruff check .` → All checks passed.
- `uv run ruff format --check .` → 32 files already formatted.
- `uv run pytest` → 94 passed.

## Next step

Human walkthrough of `./smoke_test.md` on both endpoints (`campus`, `web`) — that's the only step left for Outcome 4. Once signed off, append a closing change-log line to `../intent.md` via `/spec-intent`.
