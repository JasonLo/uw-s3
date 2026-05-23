# Intent Doc: Textual TUI best-practice audit

- **Author:** clo36@wisc.edu
- **Status:** Draft
- **Last updated:** 2026-05-22

## Problem

`src/uw_s3/tui/` was built incrementally and has never been checked end-to-end against the official Textual guidance at https://textual.textualize.io/. Threading, reactives, screens, workers, and CSS were each added when needed, so we don't know which conventions we follow, which we violate, and which we've worked around with patterns that will rot on the next Textual release. We want a focused audit + remediation pass — no new features.

## Outcome

- **WHEN** the audit of `src/uw_s3/tui/` against the Textual official docs is complete, **THE SYSTEM SHALL** produce `experiments/tui_audit/findings.md` listing each deviation with a severity tag (`blocker` / `major` / `minor`) and a citation URL on the official Textual docs site.
- **WHEN** remediation is finished, **THE SYSTEM SHALL** contain zero `blocker` and zero `major` findings; remaining `minor` items are either fixed in code or recorded as accepted exceptions in `specs/3_DECISIONS.md`.
- **WHEN** any blocking S3, filesystem, or subprocess call originates from the TUI, **THE SYSTEM SHALL** execute it inside a `@work(thread=True)` worker (or `@work()` async for coroutines) and route every UI mutation through `call_from_thread()` or `post_message()` — no direct cross-thread widget access.
- **WHILE** remediation is in progress, **THE SYSTEM SHALL** preserve every existing user-facing flow (browse, sync, mount, bucket CRUD, endpoint switch), verified by completing every checkbox in `experiments/tui_audit/smoke_test.md` on both `campus` and `web` endpoints before the branch merges.

## Non-Goals

- NOT adding new TUI features or screens.
- NOT redesigning visual style or CSS layout.
- NOT changing the CLI surface or external integrations (`rclone`, `minio`).
- NOT switching TUI frameworks or doing a Textual major-version upgrade in this pass.

## Constraints

- Constitution §Architecture reinforces outcome 3 — this audit MUST NOT relax it.
- Constitution §Stack: Python >=3.14, uv-managed, `ruff` clean.
- Reference set is the official Textual docs at https://textual.textualize.io/ matching the version pinned in `pyproject.toml` (`textual>=4.0.0`).
- Every finding MUST cite a source URL; "I think this is bad" rules are out.

## Change Log

- **2026-05-22** — Initial draft.
- **2026-05-22** — Outcome 4 now cites `experiments/tui_audit/smoke_test.md` as the regression checklist. Reason: make the "preserve every flow" outcome falsifiable.
