# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

uw-s3 is a terminal UI for UW-Madison Research Object Storage (S3). It wraps the MinIO Python client in a Textual TUI that lets users sync folders to/from S3 buckets and mount buckets as local directories via FUSE (in-process Python `s3fs` over `fsspec.fuse`).

## Code Preferences

- Use uv run to run Python scripts
- Prefer one-line docstrings for simple functions
- Use Pydantic for objects with 7+ attributes
- Always use static typing (Python 3.14+)
- Check online docs for up-to-date syntax
- Avoid unnecessary comments
- Commit when you completed a task

## Commands

```bash
uv sync                  # Install dependencies
uv run uws3              # Run the TUI (requires .env with S3 credentials)
uv run pytest            # Run tests
uv run pytest -k "name"  # Run a single test by name
uv run ruff check .      # Lint
uv run ruff format .     # Format
```

Requires Python >=3.14 and `uv` as the package manager.

## Credentials

The app reads `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` from `.env` in the current directory and `~/.config/uw-s3/.env` (via python-dotenv). Optional `S3_ENDPOINT` can be `campus` (default, UW network/VPN) or `web` (public).

## Architecture

```
src/uw_s3/
├── __init__.py          # Re-exports UWS3, ObjectInfo, endpoint constants, __version__
├── client.py            # UWS3 class — wraps MinIO client with convenience methods
├── cli.py               # Entry point: loads .env, checks for updates, restores saved endpoint, creates UWS3App, calls app.run()
├── updater.py           # Auto-update — compares installed version against latest GitHub tag
├── mount_backend.py     # Mount — runs fsspec.fuse + s3fs in a daemon thread; no external helper
├── preferences.py       # JSON persistence in ~/.config/uw-s3/preferences.json (endpoint, last_bucket)
├── validators.py        # Shared validation helpers (bucket name regex)
├── sync/
│   ├── models.py        # SyncMap dataclass (local_dir ↔ bucket mapping, auto-hashed ID)
│   ├── config.py        # JSON persistence in ~/.config/uw-s3/sync.json
│   └── engine.py        # SyncEngine — size-based diff, push/pull with callback progress
└── tui/
    ├── app.py           # UWS3App (Textual App) — holds UWS3 client + active_mounts dict
    └── screens/
        ├── base.py              # S3Screen — base screen with typed app access + threading helper
        ├── main_menu.py         # Landing screen — endpoint switcher + navigation
        ├── bucket_management.py # Bucket CRUD — list, create, delete, set permissions
        ├── file_manager.py      # Unified file manager — browse, upload/download, sync
        ├── confirm.py           # Reusable confirmation dialog
        ├── input_dialog.py      # Generic single-field modal input prompt
        └── mount.py             # FUSE mount controls (Python s3fs backend)
```

**Data flow:** `cli.py` → `UWS3App` (holds credentials + `UWS3` client) → screens access `app.s3` for all S3 operations. User preferences (endpoint, last bucket) are persisted via `preferences.py` and restored on the next launch.

## Key Patterns

- **Two S3 endpoints:** `campus.s3.wisc.edu` (UW VPN) and `web.s3.wisc.edu` (public). Switchable at runtime via main menu.
- **Textual threading:** All S3 I/O in screens uses `@work(thread=True)` with `call_from_thread()` for UI updates.
- **Screen navigation:** `push_screen()` / `pop_screen()` with `Binding("escape", "pop_screen", "Back")` on sub-screens.
- **Material-style TUI CSS:** Cards use `round` borders + `$boost` background + `border_title` for section headers. Styles are defined per-screen.
- **Sync comparison:** Size-based only (not content hashes). `SyncEngine.status_push/pull()` for dry-run, `.push()/.pull()` for execution.
- **Mount cleanup:** `UWS3App.on_unmount()` calls `Mount.unmount()` for each entry in `active_mounts` (runs `fusermount -u` and joins the FUSE handler thread). Credentials are passed to `s3fs.S3FileSystem(key=..., secret=..., client_kwargs=...)` — never written to disk.
- **Mount backend is in-process:** Python `s3fs` runs the FUSE handler inside a daemon thread in the python process — no separate helper binary, no orphan-process failure mode. If `s3fs`/`fsspec.fuse` aren't importable, the mount screen disables its Mount button. See `specs/2_INTENT/IT-2-s3fs-migration/experiments/results.md` for the prototype comparison that led to this choice.

<!-- lite-spec:pointer-block:start -->

## Read before non-trivial work

Before generating output that touches design, architecture, scope, or behavior, load the spec files lazily — they override CLAUDE.md on conflict.

- **`specs/1_CONSTITUTION.md`** — non-negotiable principles. Every change to principles MUST go through `ls-constitution`; never edit silently.
- **`specs/2_INTENT/IT-N-<slug>/intent.md`** — one folder per intent, each with its own `experiments/` subfolder. Active intents are those with `status: draft` or `status: in_progress` in the YAML frontmatter; `status` is derived by `ls-check` and MUST NOT be hand-edited. Outcomes use EARS (`WHEN <trigger> THE SYSTEM SHALL <response>`) as testable success criteria. Refine via `ls-intent`.
- **`specs/3_DECISIONS.md`** — append-only architectural choices, each tagged with the originating intent (`[intent: IT-N]`). Consult before re-litigating a settled question; supersede via `ls-decisions` rather than editing.

## Spec file ownership

Two tiers:

- **HUMAN-OWNED** — `specs/1_CONSTITUTION.md` (governance) and `specs/2_INTENT/*/intent.md` (product/scope). AI agents MUST modify these only via `/ls-constitution` and `/ls-intent` respectively. Never with direct Edit/Write/sed, not even for a "trivial sync" like fixing a stale count.
- **AGENT-WRITABLE** — `specs/3_DECISIONS.md` (engineering log). AI agents MAY append or supersede entries directly, OR via `/ls-decisions` for the guided path. Direct writes MUST follow the format in `ls-decisions`, validate against the constitution first, and only record decisions settled with the human in the current conversation (no phantom commitments).

Files outside `specs/` (README, this file, source, `SKILL.md` bodies, scripts) are fair game for normal edits.

## Spec workflow

This repo uses **lite-spec** — invoke the skills by name:

- `/ls-init` — bootstrap or repair the lite-spec setup
- `/ls-constitution` — ratify or amend principles (`specs/1_CONSTITUTION.md`)
- `/ls-intent` — draft or refine intent (`specs/2_INTENT/IT-N-<slug>/intent.md`)
- `/ls-decisions` — log a decision (`specs/3_DECISIONS.md`)
- `/ls-check` — drift report against intent + constitution

<!-- lite-spec:pointer-block:end -->
