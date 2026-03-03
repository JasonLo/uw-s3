# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

uw-s3 is a terminal UI for UW-Madison Research Object Storage (S3). It wraps the MinIO Python client in a Textual TUI that lets users sync folders to/from S3 buckets and mount buckets as local directories via rclone FUSE.

## Code Preferences

- Use uv run to run Python scripts
- Prefer one-line docstrings for simple functions
- Use Pydantic for objects with 7+ attributes
- Always use static typing (Python 3.13+)
- Check online docs for up-to-date syntax
- Avoid unnecessary comments

## Commands

```bash
uv sync                  # Install dependencies
uv run uw-s3             # Run the TUI (requires .env with S3 credentials)
uv run pytest            # Run tests
uv run pytest -k "name"  # Run a single test by name
uv run ruff check .      # Lint
uv run ruff format .     # Format
```

Requires Python >=3.14 and `uv` as the package manager.

## Credentials

The app reads `S3_ACCESS_KEY_ID` and `S3_SECRET_ACCESS_KEY` from `.env` (via python-dotenv). Optional `S3_ENDPOINT` can be `campus` (default, UW network/VPN) or `web` (public).

## Architecture

```
src/uw_s3/
├── __init__.py          # UWS3 class — wraps MinIO client with convenience methods
├── cli.py               # Entry point: loads .env, creates UWS3App, calls app.run()
├── rclone.py            # RcloneMount — generates temp rclone config, spawns rclone mount subprocess
├── sync/
│   ├── models.py        # SyncMap dataclass (local_dir ↔ bucket mapping, auto-hashed ID)
│   ├── config.py        # JSON persistence in ~/.config/uw-s3/sync.json
│   └── engine.py        # SyncEngine — size-based diff, push/pull with callback progress
└── tui/
    ├── app.py           # UWS3App (Textual App) — holds UWS3 client + active_mounts dict
    └── screens/
        ├── main_menu.py # Landing screen — endpoint switcher + navigation
        ├── sync.py      # Two-pane: DirectoryTree + bucket selector + push/pull
        └── mount.py     # Three-pane: DirectoryTree + bucket list + rclone mount controls
```

**Data flow:** `cli.py` → `UWS3App` (holds credentials + `UWS3` client) → screens access `app.s3` for all S3 operations.

## Key Patterns

- **Two S3 endpoints:** `campus.s3.wisc.edu` (UW VPN) and `web.s3.wisc.edu` (public). Switchable at runtime via main menu.
- **Textual threading:** All S3 I/O in screens uses `@work(thread=True)` with `call_from_thread()` for UI updates.
- **Screen navigation:** `push_screen()` / `pop_screen()` with `Binding("escape", "pop_screen", "Back")` on sub-screens.
- **Material-style TUI CSS:** Cards use `round` borders + `$boost` background + `border_title` for section headers. Global styles in `app.py` CSS.
- **Sync comparison:** Size-based only (not content hashes). `SyncEngine.status_push/pull()` for dry-run, `.push()/.pull()` for execution.
- **Mount cleanup:** `UWS3App.on_unmount()` terminates all rclone subprocesses and removes temp config files on exit.
- **rclone is external:** Not a Python dependency — must be on PATH. The mount screen checks `shutil.which("rclone")` and disables mount if missing.
