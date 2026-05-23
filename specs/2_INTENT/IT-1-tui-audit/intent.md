---
id: IT-1
title: Textual TUI audit
slug: tui-audit
status: complete
opened: 2026-05-22
closed: 2026-05-22
superseded_by: null
verdict_outcomes_passed: null
verdict_outcomes_total: null
verdict_checked_at: null
---

# Intent Doc: Textual TUI audit

- **Author:** clo36@wisc.edu
- **Note:** Reconstructed retroactively from `experiments/findings.md` during the IT-N folder migration. The original `2_INTENT.md` for this work was overwritten when the s3fs intent (IT-2) opened.

## Problem

The Textual TUI in `src/uw_s3/tui/` had drifted from the official Textual docs in several places. Concretely: thread workers updated widgets without checking `worker.is_cancelled`, sync cancellation bypassed the worker-state pattern, `on_unmount` ran blocking subprocess teardown on the event loop, and a handful of minor patterns (modals without Escape, unguarded `push_screen`, missing `exclusive=True`, etc.) had accumulated.

## Outcome

- **WHEN** the audit completes, **THE SYSTEM SHALL** have produced a written findings document classifying every deviation by severity (blocker / major / minor) with a Textual docs citation.
- **WHEN** the audit ships, **THE SYSTEM SHALL** have zero open major findings — each must be fixed in `src/uw_s3/tui/` or formally accepted via `specs/3_DECISIONS.md`.
- **WHEN** the audit ships, **THE SYSTEM SHALL** have every minor finding either fixed or accepted via `specs/3_DECISIONS.md`, with the disposition logged in a remediation table.
- **WHEN** the audit ships, **THE SYSTEM SHALL** pass `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest`, with the Mount flow verified against `experiments/smoke_test.md` on both `campus` and `web` endpoints.

## Non-Goals

- NOT rewriting the TUI; only correctness/idiom fixes against published Textual guidance.
- NOT replacing the test harness; Pilot stays the testing backend.
- NOT changing the rclone backend itself — that's deferred to the next intent.

## Constraints

- Method: targeted reference pass against the 8 Textual doc pages that match patterns in the codebase, then file-by-file walkthrough.
- Every finding MUST cite a specific Textual docs URL.

## Change Log

- **2026-05-22** — Audit complete; 11 findings produced (3 major, 8 minor). All major fixed, 6 minor fixed, 2 minor accepted via `specs/3_DECISIONS.md` (D-0001, D-0002). Outcome 4 Mount-flow smoke-test sign-off deferred to IT-2 (s3fs migration), where it became the migration's gating verification.
