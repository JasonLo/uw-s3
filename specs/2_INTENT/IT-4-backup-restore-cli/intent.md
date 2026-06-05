---
id: IT-4
title: Programmatic backup/restore CLI
slug: backup-restore-cli
status: draft
opened: 2026-06-05
closed: null
superseded_by: null
verdict_outcomes_passed: 0
verdict_outcomes_total: 8
verdict_checked_at: null
---

# Intent Doc: Programmatic backup/restore CLI

- **Author:** clo36@wisc.edu
- **Note:** Backfilled after implementation (`src/uw_s3/backup_ops.py`, `src/uw_s3/cli.py`, `tests/test_backup_ops.py`) to capture the intent retroactively.

## Problem

uw-s3 is TUI-only: `uws3` (`uw_s3.cli:main`) takes no arguments and immediately launches the Textual app. There is no way to back up or restore a file or folder from a script, cron job, or CI step. The core (`UWS3` client + `SyncEngine`) is already pure and UI-free, but it is locked behind the interactive app, so the two most common operations — push a folder up, pull it back down — cannot be driven programmatically.

## Outcome

- **WHEN** the user runs `uws3` with no subcommand, **THE SYSTEM SHALL** launch the existing Textual TUI with unchanged behavior.
- **WHEN** the user runs `uws3 backup <dir> s3://<bucket>/<key>` against a directory, **THE SYSTEM SHALL** upload only files missing on S3 or differing in size, skip byte-identical files, and exit 0.
- **WHEN** the user runs `uws3 backup <file> s3://<bucket>/<key>` against a regular file, **THE SYSTEM SHALL** upload it to exactly `<key>` and exit 0.
- **WHEN** the user runs `uws3 restore s3://<bucket>/<key> <dest>` and `<key>` names a single object, **THE SYSTEM SHALL** download that object, writing to `<dest>/<basename>` when `<dest>` is an existing directory, and exit 0.
- **WHEN** the user runs `uws3 restore s3://<bucket>/<key> <dest>` and `<key>` resolves to multiple objects, **THE SYSTEM SHALL** treat `<key>` as a prefix and pull every object missing locally or differing in size, and exit 0.
- **WHEN** any backup or restore command is given `--dry-run`, **THE SYSTEM SHALL** report the would-transfer and skipped counts and perform zero upload or download calls, exiting 0.
- **WHEN** any backup or restore command is given `--json`, **THE SYSTEM SHALL** print a single JSON object to stdout carrying `transferred`, `skipped`, `bytes`, `paths`, and `dry_run`.
- **IF** the s3:// URI is malformed, the local path is missing, credentials are absent, or the S3 backend errors, **THEN THE SYSTEM SHALL** write a message to stderr, exit 1, and SHALL NOT print or persist credential values.

## Non-Goals

- NOT a content-hash or timestamp diff — size-based comparison only, reusing `SyncEngine` (matches the TUI sync semantics).
- NOT deletion/mirroring — extra files on the destination are never removed (backup/restore are additive).
- NOT a new console_script — `backup`/`restore` are subcommands of the existing `uws3` entry point.
- NOT a daemon, watch mode, or scheduler — each invocation is a single-shot transfer (Constitution §7).
- NOT bucket lifecycle (create/delete/policy) or mount control — those stay TUI-only.
- NOT a progress bar with byte-level throughput — per-file lines plus a summary count suffice.

## Constraints

- **Constitution §5** — every new function, parameter, and return MUST be statically typed.
- **Constitution §6** — `BackupResult` stays under 7 attributes, so a dataclass is used rather than Pydantic.
- **Constitution §7** — the CLI is a single-shot tool with no server, daemon, or background process.
- **Constitution §9** — credentials are read only from env / `.env` (reusing the TUI's loader) and MUST NEVER be written to disk or printed, including in `--json` output.
- The headless path MUST NOT trigger the interactive auto-updater (`check_and_update()` runs only on the TUI path) so scripted callers are never blocked on a prompt.
- `--endpoint campus|web` overrides endpoint resolution; absent it, the existing preference → `S3_ENDPOINT` → campus order applies.

## Change Log

- **2026-06-05** — Initial draft, backfilled from the shipped implementation and its tests.
