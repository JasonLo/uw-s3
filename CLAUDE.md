# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

uw-s3 is a terminal UI for UW-Madison Research Object Storage (S3). It wraps the MinIO Python client in a Textual TUI that lets users sync folders to/from S3 buckets and mount buckets as local directories via rclone FUSE.

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
├── rclone.py            # RcloneMount — spawns rclone in its own process group, passes creds via env
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
        └── mount.py             # rclone mount controls
```

**Data flow:** `cli.py` → `UWS3App` (holds credentials + `UWS3` client) → screens access `app.s3` for all S3 operations. User preferences (endpoint, last bucket) are persisted via `preferences.py` and restored on the next launch.

## Key Patterns

- **Two S3 endpoints:** `campus.s3.wisc.edu` (UW VPN) and `web.s3.wisc.edu` (public). Switchable at runtime via main menu.
- **Textual threading:** All S3 I/O in screens uses `@work(thread=True)` with `call_from_thread()` for UI updates.
- **Screen navigation:** `push_screen()` / `pop_screen()` with `Binding("escape", "pop_screen", "Back")` on sub-screens.
- **Material-style TUI CSS:** Cards use `round` borders + `$boost` background + `border_title` for section headers. Styles are defined per-screen.
- **Sync comparison:** Size-based only (not content hashes). `SyncEngine.status_push/pull()` for dry-run, `.push()/.pull()` for execution.
- **Mount cleanup:** `UWS3App.on_unmount()` terminates each rclone process group (SIGTERM → SIGKILL fallback) on exit. Credentials are passed via `RCLONE_CONFIG_UWS3_*` env vars, never written to disk.
- **rclone is external:** Not a Python dependency — must be on PATH. The mount screen checks `shutil.which("rclone")` and disables mount if missing.
