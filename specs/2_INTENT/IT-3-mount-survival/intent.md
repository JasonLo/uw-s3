---
id: IT-3
title: Mount survival across TUI exits
slug: mount-survival
status: draft
opened: 2026-05-23
closed: null
superseded_by: null
verdict_outcomes_passed: 0
verdict_outcomes_total: 6
verdict_checked_at: null
---

# Intent Doc: Mount survival across TUI exits

- **Author:** clo36@wisc.edu

## Problem

Today a FUSE mount lives in a daemon thread inside the TUI process (`src/uw_s3/mount_backend.py`). The instant the user quits the TUI the kernel reaps the mount, so any open shells, file dialogs, or background scripts pointing at `./s3/<bucket>` lose access. This is the top usage friction reported on Campus and Web endpoints: users want the TUI for setup and browsing, then expect the mount to keep working while they get on with their actual data work in another terminal. The IT-2 cleanup-on-exit outcome (Outcome 3) was correct for IT-2's scope but is now the explicit thing we want to change.

## Outcome

- **WHEN** the user picks "Keep running" on the exit prompt, **THE SYSTEM SHALL** leave a detached `uws3-mount-worker` process holding the mount within 10 seconds of confirmation, and the worker SHALL still be alive (`pgrep -f uws3-mount-worker` non-empty) after the TUI process exits.
- **WHEN** the user picks "Unmount all" (default focus) on the exit prompt, **OR** no active mounts exist, **THE SYSTEM SHALL** clean up every mount within 5 seconds and leave `pgrep -f uws3-mount-worker` empty (matches IT-2 Outcome 3 for the legacy path).
- **WHEN** the TUI launches and `~/.config/uw-s3/mounts.json` references a live worker PID whose mount point is still mounted, **THE SYSTEM SHALL** surface that mount in the Active Mounts panel within 2 seconds of MountScreen opening.
- **WHEN** the user clicks Unmount on a restored (detached) mount, **THE SYSTEM SHALL** send SIGTERM to the worker and the mount point SHALL be released within 5 seconds.
- **WHEN** mount metadata is persisted, **THE SYSTEM SHALL** write only `bucket`, `endpoint`, `mount_point`, `pid`, `started_at` to `~/.config/uw-s3/mounts.json` and SHALL NEVER include S3 credentials (Constitution §9).
- **WHEN** a `mounts.json` entry references a dead PID or a mount point that no longer reports as mounted, **THE SYSTEM SHALL** remove the entry and run `fusermount -u` on the stale path before MountScreen opens.

## Non-Goals

- NOT preserving mounts across host reboot — entries pointing at dead PIDs are cleaned on next launch, not auto-remounted.
- NOT supporting multiple concurrent TUI instances managing the same worker (single-user terminal TUI assumption per §7 stays intact).
- NOT introducing an IPC channel beyond PID + POSIX signals — no Unix socket, no RPC, no shared memory.
- NOT auto-remounting on S3 connection drop (already a non-goal in IT-2; restated here so it isn't accidentally read into "survival").
- NOT changing the credentials model — env / `.env` only, per Constitution §9.
- NOT extending survival to the sync engine or any other TUI feature; only FUSE mounts.

## Constraints

- **Constitution §4** — `cleanup_or_detach_mounts()` and `restore_active_mounts()` MUST run off the Textual event loop (`@work(thread=True)` or `asyncio.to_thread`).
- **Constitution §7 + §10** — the worker MUST be the single-purpose mount worker spelled out in §10; it MUST NOT accept inbound network connections, expose any UI, or share state across users.
- **Constitution §9** — `mounts.json` MUST NOT contain S3 credentials; the worker MUST receive credentials only via the environment of its `subprocess.Popen` parent.
- The worker MUST exit on SIGTERM/SIGINT after unmounting cleanly (§10).
- Mid-run detach is implemented as in-process-unmount → subprocess-remount at the same path; a sub-second window where the mount point is briefly unavailable is acceptable. Open file handles at the mount point during that window MAY see stale-FS errors, and this trade-off SHALL be surfaced in the survival-prompt copy.
- Target platforms remain Linux (incl. WSL2 with fuse3); no Windows-native FUSE (per IT-2).

## Change Log

- **2026-05-23** — Initial draft. Opens after IT-2's in-process s3fs backend lands; needs Constitution §7 amended (carve-out + new §10) before the implementation can pass `ls-check`.
