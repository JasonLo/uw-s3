# s3fs Backend Evaluation — Results

Fill in as you exercise each prototype. The Mount checkboxes from
`experiments/tui_audit/smoke_test.md` apply here too — both backends
must pass them on both endpoints before either is a candidate.

The intent's binding targets:
- Mount → top-level listing within **3s**
- Unmount within **5s**, no orphan helpers
- No blocking the Textual event loop on app exit

## s3fs-fuse (external binary)

### campus

- Mount-to-listing latency: __ s
- Unmount latency: __ s
- Orphan processes after unmount (`pgrep -f s3fs`): __
- Stale/empty listings observed? __
- External writes (from `mc` / TUI) appear after re-list? __
- Setup notes (install steps, FUSE perms, kernel module quirks): __
- Failure-mode quality (force 403, bad endpoint, missing FUSE): __

### web

- Mount-to-listing latency: __ s
- Unmount latency: __ s
- Orphan processes after unmount: __
- Stale/empty listings observed? __
- External writes appear after re-list? __
- Setup notes: __
- Failure-mode quality: __

## Python s3fs (fsspec, in-process)

### campus

- Mount-to-listing latency: __ s
- Unmount latency: __ s
- Orphan processes after unmount (`pgrep -f s3fs`): __
- Stale/empty listings observed? __
- External writes appear after re-list? __
- Setup notes (deps, FUSE perms, fsspec.fuse caveats): __
- Failure-mode quality: __

### web

- Mount-to-listing latency: __ s
- Unmount latency: __ s
- Orphan processes after unmount: __
- Stale/empty listings observed? __
- External writes appear after re-list? __
- Setup notes: __
- Failure-mode quality: __

## Comparison summary

Fill in once both backends are exercised.

| Axis | s3fs-fuse | Python s3fs |
| --- | --- | --- |
| Both endpoints meet 3s mount target? | __ | __ |
| Both endpoints meet 5s unmount target? | __ | __ |
| Zero orphan helpers? | __ | __ |
| Listing freshness acceptable? | __ | __ |
| Setup friction (rough rank) | __ | __ |
| Failure messaging | __ | __ |
| Notes / surprises | __ | __ |

## Recommendation

Backend chosen: __ (s3fs-fuse | Python s3fs | neither — re-plan)

Reason (one paragraph, citing the numbers above): __

Once filled in, log this as **D-0003** in `specs/3_DECISIONS.md` via
`/ls-decisions`. Then resume the plan at Phase 4.
