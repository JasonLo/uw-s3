# Constitution: uw-s3

Ratified: 2026-05-22

Non-negotiable project principles. Every other `ls-` skill validates its output against this file and refuses to produce violating output.

This is a lean constitution for a small, rapid-prototyping Python project. It locks in only the rules whose violation would cost real time or trust: the toolchain, the threading rule that keeps the TUI responsive, the type discipline, the scope fence that stops the project from sprawling, and the credential-handling rule.

## Stack choice

1. Python MUST be >=3.14.
2. `uv` MUST be the package manager; `pip install`, `poetry`, and `conda` MUST NOT be used to manage project dependencies.
3. Code MUST pass `uv run ruff check .` and `uv run ruff format --check .` before commit.

## Architecture

4. All blocking I/O initiated from a Textual screen (S3 calls, filesystem scans, subprocess spawns) MUST run on a background thread via `@work(thread=True)`, with UI updates marshalled through `call_from_thread()`.

## Code quality

5. All function parameters and return types MUST carry static type annotations.
6. Objects with 7 or more attributes MUST be modeled with Pydantic.

## Boundaries

7. ~~The project MUST remain a single-user terminal TUI; a web UI, REST server, or background daemon MUST NOT be added.~~ [superseded 2026-05-23]
   The project MUST remain a single-user terminal TUI; a web UI, REST server, or general-purpose background daemon MUST NOT be added. The narrow exception is §10.
8. ~~`rclone` MUST stay an external binary discovered on `PATH`; it MUST NOT be vendored, bundled, or wrapped as a Python dependency.~~ [superseded 2026-05-22]
   FUSE mount helpers MAY be external binaries on `PATH` or in-process Python libraries. The mount backend MUST NOT block the Textual event loop (§4 still binds) and MUST NOT write S3 credentials to disk (§9 still binds).

## Security

9. S3 credentials MUST be read from environment variables or `.env` files; the application MUST NEVER write credentials to disk or log them to stdout/stderr.

## Mount workers

10. A single-purpose detached mount worker spawned by the TUI MAY outlive the TUI process. Each worker MUST service exactly one FUSE mount, MUST NOT accept inbound network connections, MUST NOT expose any UI, MUST NOT share state across users, and MUST exit on receipt of SIGTERM or SIGINT after unmounting cleanly. The worker's metadata (bucket, endpoint, mount point, PID, started_at) MAY be persisted under `~/.config/uw-s3/`; §9 still binds — S3 credentials MUST NEVER be persisted there.

## Amendments

- **2026-05-22** — Initial constitution ratified.
- **2026-05-22** — §8 generalized from rclone-specific to backend-agnostic. The durable safety invariants (no blocking the Textual event loop, no S3 credentials on disk) are kept; the choice between external-binary and in-process Python mount helpers is now data-driven per `specs/2_INTENT/IT-2-s3fs-migration/intent.md`. Reason: rclone is being replaced with one of two `s3fs` flavors, and the old §8 blocked both the rclone removal and the in-process candidate before evaluation could happen.
- **2026-05-23** — §7 carve-out + §10 added. §7's blanket "no background daemon" blocked the IT-3 goal of making an active mount survive a TUI exit. The amendment keeps the general prohibition but allows a single-purpose mount worker, with the worker's contract spelled out in the new §10 so the carve-out can't be reused as a backdoor for arbitrary background services. Reason: IT-3 mount-survival; mounts dying when the user closes the TUI is the top friction point in current usage.
