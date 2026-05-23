# PRD: Lite-spec intents as folders, experiments nested, status derived by `ls-check`

- **Author:** clo36@wisc.edu
- **Status:** Draft
- **Last updated:** 2026-05-22
- **Target repo:** the lite-spec skills repo (skills installed at `~/.claude/skills/ls-*`). This document is a hand-off — the case study is uw-s3, but the changes land in the skill definitions, not here.

## Problem

The lite-spec workflow leaks history on two axes:

1. **Experiments are unmoored.** `experiments/<name>/` lives at repo root with no convention linking it to the intent it backs. After two intents, uw-s3 already has orphaned folders (`experiments/tui_audit/`, `experiments/s3fs_eval/`) whose only tie to their motivating intent is prose inside `specs/2_INTENT.md` — and `2_INTENT.md` only describes the *current* intent.
2. **Completed intents are overwritten.** `specs/2_INTENT.md` is a single file. When intent A finishes and intent B begins, A's content disappears. Today's `2_INTENT.md` in uw-s3 literally name-drops "the previous (Complete) Textual TUI audit intent" with no surviving record of what that was.

Together these mean the spec workflow forgets the design conversation as soon as the conversation moves on.

## Outcome (EARS)

- **WHEN** a user runs `/ls-intent new "<title>"`, **THE SYSTEM SHALL** create a folder at `specs/2_INTENT/IT-N-<slug>/` (where `N` is the next monotonic integer and `<slug>` is a kebab derivation of the title) containing `intent.md` (with `status: draft` and the new frontmatter) and an empty `experiments/` subfolder.
- **WHEN** a user runs `/ls-intent supersede --intent IT-N --by-new "<title>"`, **THE SYSTEM SHALL** flip `IT-N` to `status: superseded`, set `superseded_by: IT-M` to the newly-created successor's ID, and create `IT-M-<slug>/` with `status: draft`.
- **WHEN** a user runs `/ls-decisions "<text>"` with exactly one *open* intent (status `draft` or `in_progress`), **THE SYSTEM SHALL** append the decision to `specs/3_DECISIONS.md` with a trailing `[intent: IT-N]` tag derived from that intent.
- **WHEN** a user runs `/ls-decisions "<text>"` with zero or multiple open intents, **THE SYSTEM SHALL** prompt for an intent ID or require `--intent IT-N`.
- **WHEN** a user runs `/ls-check` without `--intent`, **THE SYSTEM SHALL** iterate every intent folder whose status is not `complete` or `superseded`, compute drift findings per intent, derive `status` from outcome pass-count, and rewrite the frontmatter fields `status`, `verdict_outcomes_passed`, `verdict_outcomes_total`, `verdict_checked_at`, and `closed`.
- **WHEN** a user runs `/ls-check --intent IT-N`, **THE SYSTEM SHALL** perform the same update on only that intent.
- **WHEN** `/ls-check` derives `status: complete` for an intent, **THE SYSTEM SHALL** set `closed` to the current ISO date; **WHEN** a subsequent run derives any non-`complete` status for the same intent, **THE SYSTEM SHALL** clear `closed` back to `null`.
- **WHEN** the new layout ships, **THE SYSTEM SHALL** retain no fallback for the old flat `specs/2_INTENT.md` path in any `ls-*` skill.

## Non-Goals

- NOT building a migration command (`ls-migrate`). Existing repos migrate by hand.
- NOT supporting human-verified outcome tags (e.g., `[verified-by: smoke_test.md]`). v1 treats all EARS outcomes the same — if `ls-check` finds no drift findings against an outcome, it counts as passing.
- NOT scoping `1_CONSTITUTION.md` per-intent. The constitution remains project-wide.
- NOT splitting `3_DECISIONS.md` into per-intent files. It stays a single append-only log; the `[intent: IT-N]` suffix enables `grep`-style filtering.
- NOT allowing the user to hand-edit `status`, `verdict_*`, or `closed` fields — those are skill-managed. `superseded_by` is the one frontmatter field the user (via `/ls-intent supersede`) sets.
- NOT enforcing a single active intent. Multiple intents may be `draft` or `in_progress` concurrently.

## Design

### On-disk layout

```
specs/
  1_CONSTITUTION.md
  2_INTENT/
    IT-1-tui-audit/
      intent.md                 # status: complete
      experiments/
        smoke_test.md
        findings.md
    IT-2-s3fs-migration/
      intent.md                 # status: active (in_progress or complete)
      experiments/
        README.md
        results.md
        try_s3fs_python.py
        try_s3fs_fuse.sh
  3_DECISIONS.md
```

Root-level `experiments/` no longer exists. Every experiment nests under the intent it backs.

### Intent identifier

- Canonical handle: `IT-N` (`IT` prefix, monotonic integer, no zero-padding — `IT-1` not `IT-001`).
- Folder name: `IT-N-<slug>`. `<slug>` is a kebab-case derivation of the title — lowercase ASCII, hyphen-separated, alphanumerics + hyphens only. `ls-intent new` MUST truncate to ≤40 chars at a word boundary (split on `-`, drop trailing tokens until ≤40) rather than rejecting long titles. Folder name is immutable after creation; rename would invalidate `[intent: IT-N]` references and the `superseded_by` chain.
- Skills resolve `IT-N` → folder via prefix glob (`specs/2_INTENT/IT-N-*`). Unique by ID.
- `ls-intent new` auto-assigns the next `IT-N` by scanning existing folders and taking `max(N) + 1`. No user input required for the ID.

### `intent.md` frontmatter

```yaml
---
id: IT-2
title: S3 mount backend — replace rclone with s3fs
slug: s3fs-migration
status: in_progress            # draft | in_progress | complete | superseded
opened: 2026-05-22
closed: null                   # set by ls-check on flip to complete; cleared on flip away
superseded_by: null            # e.g., IT-3
verdict_outcomes_passed: 3
verdict_outcomes_total: 5
verdict_checked_at: 2026-05-22T18:30:00Z
---
```

Body below the frontmatter keeps the existing intent.md structure: Problem / Outcome (EARS) / Non-Goals / Constraints / Change Log.

### Status state machine

```
ls-intent new                           ls-intent supersede --intent IT-N
   │                                              │
   ▼                                              ▼
[ draft ] ──ls-check (some pass)──> [ in_progress ] ──all pass──> [ complete ]
                                            │                          │
                                            └───── ls-intent supersede ┘
                                                       │
                                                       ▼
                                                 [ superseded ]
```

- `draft`, `in_progress`, `complete` are **derived** by `ls-check`. The user never writes them.
- `superseded` is the only manually-set value (`/ls-intent supersede`).
- Status can move backward: a `complete` intent that later acquires drift flips back to `in_progress`. This is the regression-detection feature — the workflow notices when shipped intents stop holding.
- "Passing" an outcome = `ls-check` produces zero drift findings against it.

### Skill changes

| Skill | After |
|---|---|
| `ls-init` | Scaffolds `specs/{1_CONSTITUTION.md, 2_INTENT/, 3_DECISIONS.md}`. No root-level `experiments/`. Empty `2_INTENT/` is valid. |
| `ls-intent` | Subcommands: `new <title>` (creates `IT-N-<slug>/`, status `draft`); `refine [--intent IT-N]` (edits content, prompts on ambiguity); `supersede --intent IT-N --by-new <title>` (flips status, opens successor). `complete` subcommand is **removed** — completion is derived by `ls-check`. |
| `ls-check` | Without `--intent`: iterates every non-`complete`, non-`superseded` intent; checks drift; derives status; rewrites frontmatter. With `--intent IT-N`: same, scoped to one. Constitution check unchanged. |
| `ls-decisions` | Append `D-NNNN: …` with trailing `[intent: IT-N]` tag. Auto-fills tag from the single open intent (status `draft` or `in_progress`) when unambiguous; otherwise prompts or accepts `--intent IT-N`. Pre-existing untagged lines remain valid (skill tolerates them on read). |
| `ls-constitution` | Unchanged. |

### Decision log format

```
- **D-0003:** Decided to replace rclone with Python s3fs because … (2026-05-22). [intent: IT-2]
```

The log stays a single append-only file. The tag lets `grep '\[intent: IT-2\]' specs/3_DECISIONS.md` enumerate one intent's decisions in one shell command.

## Constraints

- The `IT-N-<slug>` folder name is immutable post-creation. Renaming breaks the decision-log references and `superseded_by` chain.
- `status`, `verdict_*`, and `closed` are skill-managed fields — user edits to those values may be overwritten on the next `ls-check` run. Skills SHOULD NOT silently ignore manual edits, but SHALL document this contract in their help text.
- Multi-active is first-class. Skills that historically assumed "one active intent" (`ls-check`, `ls-decisions`) MUST handle the zero / one / many cases explicitly — prompt, accept a flag, or iterate.
- Legacy / untagged `D-NNNN` entries in `3_DECISIONS.md` MUST remain readable. Adding the `[intent: IT-N]` requirement applies only to new entries written by the updated `ls-decisions`.

## Acceptance criteria

1. `/ls-init` on an empty repo creates `specs/{1_CONSTITUTION.md, 2_INTENT/, 3_DECISIONS.md}` and no root-level `experiments/`.
2. `/ls-intent new "Replace rclone with s3fs"` creates `specs/2_INTENT/IT-1-replace-rclone-with-s3fs/{intent.md, experiments/}` with `id: IT-1`, `status: draft`.
3. A second `/ls-intent new "<title>"` produces `IT-2-…/` (auto-monotonic ID assignment).
4. `/ls-check` with two intents under `IT-1-…/` and `IT-2-…/` updates `status`, `verdict_outcomes_passed`, `verdict_outcomes_total`, and `verdict_checked_at` in each intent.md — without `--intent` flag.
5. `/ls-check --intent IT-2` updates only `IT-2-…/intent.md`.
6. `/ls-decisions "Decided X"` with two non-terminal intents prompts for the intent ID (or accepts `--intent IT-2`); the appended `D-NNNN` line ends with `[intent: IT-2]`.
7. `/ls-intent supersede --intent IT-2 --by-new "<title>"` flips IT-2 to `status: superseded`, sets `superseded_by: IT-3`, and creates `IT-3-…/` with `status: draft`.
8. `/ls-check` derives `status: complete` for a fully-passing intent and sets `closed` to today's ISO date. A subsequent edit that introduces drift flips it back to `in_progress` and clears `closed`.
9. `grep '\[intent: IT-2\]' specs/3_DECISIONS.md` lists every decision logged against IT-2.

## Change Log

- **2026-05-22** — Initial draft. Captures the design conversation from the uw-s3 case study.
