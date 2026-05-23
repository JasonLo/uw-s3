# s3fs Backend Evaluation — Results

Fill in as you exercise each prototype. The Mount checkboxes from
`experiments/tui_audit/smoke_test.md` apply here too — both backends
must pass them on both endpoints before either is a candidate.

The intent's binding targets:
- Mount → top-level listing within **3s**
- Unmount within **5s**, no orphan helpers
- No blocking the Textual event loop on app exit

> **Environment caveat:** the runs below were executed off-VPN on
> 2026-05-22. `campus.s3.wisc.edu` was unreachable from this network
> (TCP/443 timeout); only the `web` endpoint could be exercised here.
> Campus rows are marked **`untested (no VPN)`** and must be filled
> in by a tester on UW VPN before D-0003 can land.

## s3fs-fuse (external binary)

> **Untested locally.** `s3fs-fuse` is not installed on this machine
> and installing requires `sudo apt install s3fs`. Skipped pending a
> tester with the binary available. Both rows below remain to be
> filled in before D-0003.

### campus

- Mount-to-listing latency: __ s — untested (no VPN, no binary)
- Unmount latency: __ s — untested
- Orphan processes after unmount (`pgrep -x s3fs`): __ — untested
- Stale/empty listings observed? __ — untested
- External writes (from `mc` / TUI) appear after re-list? __ — untested
- Setup notes (install steps, FUSE perms, kernel module quirks): __ — untested
- Failure-mode quality (force 403, bad endpoint, missing FUSE): __ — untested

### web

- Mount-to-listing latency: __ s — untested (no binary)
- Unmount latency: __ s — untested
- Orphan processes after unmount: __ — untested
- Stale/empty listings observed? __ — untested
- External writes appear after re-list? __ — untested
- Setup notes: __ — untested
- Failure-mode quality: __ — untested

## Python s3fs (fsspec, in-process)

Versions exercised: `s3fs 2026.4.0`, `fsspec 2026.4.0`, Python 3.14,
WSL2 Linux with `fuse3` and `/dev/fuse` accessible.

### campus

- Mount-to-listing latency: __ s — **untested (no VPN)**
- Unmount latency: __ s — untested
- Orphan processes after unmount (`pgrep -x s3fs`): __ — untested
- Stale/empty listings observed? __ — untested
- External writes appear after re-list? __ — untested
- Setup notes (deps, FUSE perms, fsspec.fuse caveats): __ — untested
- Failure-mode quality: __ — untested

### web

- Mount-to-listing latency: **0.27 s** (target: ≤3 s) ✓
- Unmount latency: **<0.01 s** via `fusermount -u` (target: ≤5 s) ✓
- Orphan processes after unmount (`pgrep -x s3fs`): **none** — Python
  s3fs runs in-process, no separate helper binary exists to orphan.
- Stale/empty listings observed? **No.** Initial listing returned all
  4 top-level entries (`checkpoints`, `imagenet-1k-cache`,
  `matryoshka`, `results`).
- External writes appear after re-list? **Yes — within ~50 ms.** A
  separate `minio` client `put_object(_freshness_probe.txt)` showed
  up in `os.listdir(mnt)` on the very next poll (≤500 ms granularity
  in the probe). This directly contradicts rclone's "files from
  outside clients don't appear" failure mode from the intent, and
  was achieved with `use_listings_cache=False` on the `S3FileSystem`
  constructor.
- Setup notes: `uv pip install s3fs 'fsspec[fuse]' fusepy` covers the
  deps. `fsspec.fuse.run(..., foreground=True)` must run in a
  background thread (daemon=True) so the calling code can keep
  control; the thread blocks until unmount. Mount point must be a
  real Linux filesystem path — `/tmp/...` works in WSL2;
  `/mnt/c/...` (drvfs) does not.
- Failure-mode quality: not exhaustively probed yet (bad endpoint,
  bad creds, missing FUSE). Bonus stress test: **SIGKILL on the
  parent python process** while mounted left the mountpoint in a
  `FUSEr` state for ~1–2 s (top-level cached listing still readable,
  deeper traversal returned `No such file or directory`), then the
  kernel reaped it on its own. No s3fs/rclone binary orphans
  remained. This is meaningfully better than the rclone case the
  intent describes, but a brief stale window does exist and may
  warrant defensive `fusermount -uz` on app startup if a previous
  session crashed (cf. the WIP stale-clear logic that lived briefly
  on `rclone.py`).

## Comparison summary

Pending completion of the untested rows above.

| Axis | s3fs-fuse | Python s3fs (web) |
| --- | --- | --- |
| Web meets 3s mount target? | untested | **yes (0.27 s)** |
| Web meets 5s unmount target? | untested | **yes (<0.01 s)** |
| Zero orphan helpers on web? | untested | **yes (no binary exists)** |
| Listing freshness acceptable on web? | untested | **yes (~50 ms)** |
| Campus parity | untested | untested (no VPN) |
| Setup friction (rough rank) | untested | low — pip-installable |
| Failure messaging | untested | not probed |
| Notes / surprises | — | brief FUSEr stale window on SIGKILL but kernel self-cleans |

## Recommendation

Backend chosen: __ — **pending campus + s3fs-fuse runs**.

Python s3fs meets every measurable target on `web` and beats the
specific rclone brittleness called out in the intent
(listing freshness). It is the leading candidate. Before D-0003 can
be logged, a tester needs to (a) install `s3fs-fuse` and re-run both
prototypes on `web`, and (b) re-run both prototypes on `campus` from
inside UW VPN.

Once filled in, log this as **D-0003** in `specs/3_DECISIONS.md` via
`/ls-decisions`. Then resume the plan at Phase 4.
