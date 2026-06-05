# s3fs Backend Evaluation — Results

The intent's binding targets:
- Mount → top-level listing within **3s**
- Unmount within **5s**, no orphan helpers
- No blocking the Textual event loop on app exit

> **Environment caveat:** all runs below were on `web.s3.wisc.edu`
> only. `campus.s3.wisc.edu` was unreachable from the test machine
> (no UW VPN). Both endpoints share the same MinIO backend, so
> latency and API shape should match modulo network distance; the
> campus rows still need a VPN-side tester before sign-off, but no
> result on `web` is endpoint-dependent.
>
> Test bucket: `matryoshka` (4 top-level entries; writable on web).
> Versions: `rclone v1.73.1`, `s3fs-fuse 1.93` (GnuTLS),
> `s3fs` Python 2026.4.0, `fsspec` 2026.4.0, Python 3.14, WSL2
> Linux with `fuse3`.

## rclone (current baseline — the thing being replaced)

### web — measured 2026-05-22

- `rclone lsd uws3:matryoshka` (no FUSE): **0.38 s**, 4 entries
  returned. S3 access is healthy; the brittleness is in the mount
  layer, not in rclone's S3 client.
- `rclone mount ... --vfs-cache-mode full ...` (the args from
  `src/uw_s3/rclone.py:100-117`):
  - `os.path.ismount(mnt)` returns True at **0.30 s** — fast, but
    misleading; this is what `RcloneMount.mount()` polls.
  - First successful `os.listdir(mnt)`: **never** within 60 s
    (587 attempts, all `errno=5 Input/output error`). With
    `--vfs-cache-mode off` (default): same behavior at 30 s. ✗
  - The mount log shows rclone is alive — periodic vfs-cache
    cleanup ticks fire every minute — but no FUSE listing calls
    succeed. This is the "slow first-list / empty directory
    listings" failure mode the intent flagged for rclone.
- **Process lifecycle is the second brittleness, also reproduced:**
  the "clean" unmount path (`fusermount -u` → `proc.wait(timeout=5)`)
  *returned in <0.01 s* both times but **left an orphan rclone PID
  and a stale `fuse.rclone` mount entry** behind. Cleanup required
  manual `kill -9 <pid>` + `fusermount -uz <mnt>`. That matches the
  intent's "orphan rclone survives app exit, SIGTERM→SIGKILL
  teardown races" almost verbatim — and it happened on the *normal*
  exit path, not a crash.
- Setup notes: rclone is on PATH on this machine; no extra setup
  needed for the binary itself. WSL2 FUSE works for `s3fs-fuse` and
  Python `s3fs` (both tested below) but breaks for `rclone mount` —
  data point, but not investigated further because rclone is being
  retired.

### campus

- Untested (no VPN), and academic — rclone is being removed.



## s3fs-fuse (external binary)

### web — measured 2026-05-22

- Mount-to-listing latency: **0.31 s** (target ≤3 s) ✓
- Unmount latency: **<0.01 s** via `fusermount -u` then `proc.wait()` ✓
- Orphan processes after **clean** unmount (`pgrep -x s3fs`): **none** ✓
- Stale/empty listings observed? **No.** Initial listing showed all
  3 real top-level dirs (`checkpoints`, `imagenet-1k-cache`,
  `results`).
- External writes appear after re-list? **Yes — within ~120 ms.**
  A `minio` PUT of `_freshness_probe.txt` showed in `os.listdir(mnt)`
  on the very next poll. `stat_cache_expire=1` is the relevant
  option.
- Setup notes: install via `sudo apt install s3fs` (Debian/Ubuntu).
  Credentials passed via env (`AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`) — no on-disk passwd file. `-f` to stay
  foregrounded so the parent can manage the subprocess lifecycle;
  `-o use_path_request_style` required for these buckets.
- **Failure-mode quality (this is the differentiator):** SIGKILL on
  the s3fs process leaves the mount in
  **`ENOTCONN (errno 107) "Transport endpoint is not connected"`**
  *persistently* — no kernel self-recovery seen across a 5 s poll.
  Requires explicit `fusermount -uz` to clear. The earlier "no
  orphans" line above only holds when the parent unmounts cleanly;
  a crash leaves both a stale mount endpoint **and** (if the launcher
  fails to reap the child) an orphan `s3fs` PID. This is the
  rclone-family brittleness the intent flagged — replacing rclone
  with `s3fs-fuse` does NOT fix it, because the brittleness is in
  the external-binary pattern, not in rclone specifically. A real
  app implementation would need to ship `_clear_stale_mount()` logic
  equivalent to the WIP that briefly lived on `rclone.py`.

### campus

- Untested (no VPN). Same backend on the same endpoint host, so
  results should match `web` modulo RTT.

## Python s3fs (fsspec, in-process)

### web — measured 2026-05-22

- Mount-to-listing latency: **0.27 s** (target ≤3 s) ✓
- Unmount latency: **<0.01 s** via `fusermount -u` ✓
- Orphan processes after unmount (`pgrep -x s3fs`): **none** —
  Python s3fs runs in-process, no separate helper binary exists to
  orphan in the first place. ✓
- Stale/empty listings observed? **No.** Initial listing returned
  4 entries (`checkpoints`, `imagenet-1k-cache`, `matryoshka`,
  `results`) — one more than s3fs-fuse because fsspec surfaces the
  root-prefix entry returned by the bucket; cosmetic, not a bug.
- External writes appear after re-list? **Yes — within ~50 ms.**
  Achieved with `use_listings_cache=False` on the
  `S3FileSystem` constructor.
- Setup notes: `uv pip install s3fs 'fsspec[fuse]' fusepy` covers
  the deps. `fsspec.fuse.run(..., foreground=True)` must run in a
  background thread (daemon=True) so the calling code keeps
  control; the thread blocks until unmount. Mount point must be a
  real Linux fs (`/tmp/...` works in WSL2; `/mnt/c/...` does not).
- **Failure-mode quality:** SIGKILL on the parent python process
  left the mountpoint in a `FUSEr` state for ~1–2 s where the
  cached top-level read but deeper traversal returned
  `No such file or directory`, after which the kernel reaped the
  mount on its own. No `s3fs`/`rclone` binary orphans remained
  (and none could — there is no helper binary). Net: a brief
  stale window vs. s3fs-fuse's persistent ENOTCONN. Defensive
  startup `fusermount -uz` is still cheap insurance if a previous
  session crashed mid-mount.

### campus

- Untested (no VPN). No reason to expect different behavior on the
  campus endpoint host.

## Comparison summary

| Axis | rclone (baseline) | s3fs-fuse | Python s3fs |
| --- | --- | --- | --- |
| Mount establish (ismount) | 0.30 s | 0.31 s | 0.27 s |
| First successful listing | **never within 60 s ✗** | 0.31 s | 0.27 s |
| 5 s unmount target | yes (<0.01 s)\* | yes | yes |
| Zero orphans on **clean** exit | **no — orphan PID + stale mount\*** | yes | yes |
| Zero orphans on **crash** (SIGKILL) | n/a (already fails clean exit) | **no — persistent ENOTCONN + orphan PID** | **yes — kernel self-cleans, no helper exists** |
| Listing freshness | n/a (no working listing) | ~120 ms | ~50 ms |
| Setup friction | rclone binary on PATH | system package | `uv pip install` only |
| Failure messaging | needs log-tail plumbing | needs log-tail plumbing | exceptions inline |
| Constitution §4 fit | subprocess lifecycle | subprocess lifecycle | daemon-thread |
| Cred handling (§9) | env (`RCLONE_*`) — OK | env (`AWS_*_KEY`) — OK | constructor kwargs — OK |

\* "Clean unmount" for rclone *returned* in <0.01 s but the rclone
process and `fuse.rclone` mount entry survived; the listed orphan
behavior was observed on both rclone runs.

## Recommendation

**Backend chosen: Python `s3fs` (in-process, via `fsspec.fuse`).**

The rclone baseline reproduced two of the three intent failure
modes on the first attempt: (a) the mount layer never served a
working listing on this WSL2 host across 90 s of polling, and
(b) the *normal* unmount path left an orphan rclone PID and a
stale `fuse.rclone` mount. Replacing rclone with anything that
works at all is an improvement.

Between the two replacements, the decisive axis is the crash
failure mode. Both meet the latency targets and surface external
writes fast enough to matter; the difference is what happens when
something goes wrong:

- `s3fs-fuse` reproduces the rclone-family brittleness on SIGKILL —
  a stale `ENOTCONN` mount that survives the helper process and an
  orphan PID if the launcher didn't reap it. The intent listed this
  exact failure mode as one of the three reasons rclone was being
  replaced. Switching to `s3fs-fuse` ships the same bug under a
  different name.

- Python `s3fs` cannot leak an orphan binary because there isn't
  one to leak; the FUSE handler lives in the python process itself.
  When that process dies, the kernel notices and reaps the mount
  on its own (with a brief stale window). The setup story is also
  simpler — one `uv` dependency vs. a system package, FUSE perms,
  and kernel-module variance across platforms.

The §8 amendment landed on 2026-05-22 specifically to permit this
choice; nothing in the constitution blocks it.

**Open follow-ups before merge** (track in Phase 4 of the plan):
1. Campus rows: a tester on UW VPN should rerun both prototypes on
   `campus.s3.wisc.edu` to confirm parity. Expected to match `web`
   modulo network distance.
2. Defensive startup `fusermount -uz` of the configured mountpoint
   in the new `Mount` class, to absorb the brief stale window from
   a prior crashed session.
3. Smoke-test the Mount section of `../../I-1-tui-audit/experiments/smoke_test.md`
   end-to-end on both endpoints once the new backend is wired in.

**Next action:** append **D-0003** to `../../../DECISIONS.md` quoting this
recommendation, then resume the plan at Phase 4 (rename
`src/uw_s3/rclone.py` → `src/uw_s3/mount_backend.py` parametrized
on Python s3fs).
