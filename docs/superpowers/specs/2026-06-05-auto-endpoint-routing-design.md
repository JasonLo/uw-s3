# Design: Automatic per-bucket endpoint routing

**Date:** 2026-06-05
**Status:** Approved (brainstorming) — implementation in progress
**Suggested intent:** IT-4 (ratify via `/ls-intent`)

## Problem

UW Research Object Storage exposes two endpoints:

- `campus.s3.wisc.edu` — reachable only on the UW network / VPN.
- `web.s3.wisc.edu` — reachable from anywhere on the public internet.

A bucket is created as **either** a campus bucket **or** a web bucket and is
reachable only through its matching endpoint
([UW KB](https://kb.wisc.edu/researchdata/134390)). Today the TUI binds to one
endpoint at a time and forces the user to manually switch (the `e` key / the
`EndpointBar`) and to *know* which domain each bucket lives on. If they are on
the wrong endpoint the bucket simply isn't listed.

## Goal

1. Detect which endpoints the current machine can actually reach.
2. Probe each reachable endpoint for its buckets using the same credentials.
3. Remember the bucket → endpoint map so operations route automatically and the
   app still *knows about* buckets whose endpoint is currently unreachable.
4. Remove every UI that asks the user to pick a bucket's domain — the only
   remaining domain prompt is **bucket creation**, where the domain is an
   inherent, un-detectable choice.

## Approach

`app.s3` changes from a single endpoint-bound `UWS3` to an **`S3Router`** facade
that owns one `UWS3` per endpoint plus a `BucketRegistry`, and routes each
bucket-scoped call to the correct endpoint. Call sites keep calling
`app.s3.<method>(bucket, ...)`; the global endpoint switcher is removed.

### Components

**`bucket_registry.py` (new) — state, persistence, merge logic (no network).**

- `BucketEntry(name, endpoint, reachable)` dataclass (3 attrs — under the 7-attr
  Pydantic rule, §6).
- Persists the bucket → endpoint map to `~/.config/uw-s3/buckets.json` (same JSON
  pattern as `preferences.py` / `mounts_config.py`; **no credentials**, §9).
- `merge_probe(reachable_endpoints, listed)`:
  - set `map[bucket] = endpoint` for every bucket a reachable endpoint listed;
  - drop map entries that point at a reachable endpoint but were *not* listed
    (the bucket was deleted);
  - **keep** entries whose endpoint is unreachable (campus buckets persist
    off-VPN);
  - persist.
- Queries: `endpoint_for(name)`, `entries()`, `reachable_endpoints`,
  `is_reachable(name)`, `register(name, endpoint)`, `remove(name)`.

**`s3_router.py` (new) — clients, probing, routing.** `S3Router`:

- Lazily builds/caches a `UWS3` per endpoint from the session credentials.
- `probe()` (blocking; called from a worker thread, §4): for each endpoint, a
  fast TCP connect to `:443` with a short timeout; if it connects, `list_buckets()`.
  `reachable` = list succeeded. Socket-fail or list-error → unreachable, with the
  error retained for the status bar. Feeds results to `registry.merge_probe`.
- `client_for(bucket)` → routes via the registry; raises `EndpointUnreachable`
  with a "connect to UW VPN" hint when the bucket's endpoint is not reachable.
- `client(endpoint)` → the per-endpoint client (used by the create flow).
- Delegates the bucket-scoped methods screens call (`list_objects_detail`,
  `upload_file`, `download_file`, `delete_object`, `delete_prefix`,
  `rename_object`, `rename_prefix`, `empty_bucket`, `set_bucket_policy`,
  `delete_bucket`). `bucket_exists(name, *, endpoint=None)` and
  `create_bucket(name, *, endpoint)` take an explicit endpoint for new names.
- `list_buckets()` → registry union (names). `entries()` → annotated list.
  `endpoint_for(bucket)` for the mount/sync flows.

**`NetworkBar` (replaces interactive `EndpointBar` in `base.py`).** Passive
status line driven by the router's probe state:

- both reachable → `Network: Campus + Web reachable`
- web only → `Network: Web only — campus buckets need UW VPN`
- campus only → `Network: Campus only`
- neither → `Network: offline — no endpoints reachable`

The `e` binding, `action_switch_endpoint`, `switch_endpoint`,
`on_endpoint_switched`, and `_update_endpoint_bar` are removed. `S3Screen` gains
`_update_network_bar()`, an overridable `reload_buckets()` hook, and
`refresh_for_probe()` (= update bar + reload).

### Data flow

- **`cli.py`**: drop `_resolve_endpoint` and the endpoint argument; build the
  router from credentials only. The `S3_ENDPOINT` env var and the saved
  `endpoint` preference become obsolete (removed; README updated).
- **`app.py`**: `self.s3 = S3Router(...)`. `on_mount` renders from the cached
  registry immediately, then `start_probe()` launches a background
  `@work(thread=True)` probe; on completion it calls `refresh_for_probe()` on the
  active `S3Screen`. Remove `endpoint_label` / `switch_endpoint` / endpoint
  preference. Mount restore/detach is unchanged — `MountRecord.endpoint` is
  per-mount.
- **`file_manager.py` / `bucket_management.py` / `mount.py`**: bucket lists show
  the **union**, each row annotated with its domain and greyed + hinted when its
  endpoint is unreachable. Ops route through the router by bucket;
  `_make_engine` and the mount call use `router.endpoint_for(bucket)` and
  `router.client_for(bucket)`. Acting on an unreachable bucket surfaces the VPN
  hint. `Refresh` (`r`) re-probes (so connecting to the VPN and hitting refresh
  reveals campus buckets).
- **Create flow** (`bucket_management.py`): keeps a campus/web `Select` —
  defaulting to the reachable endpoint (web if it's the only one) — then
  `router.create_bucket(name, endpoint=...)` registers the new bucket.

## Edge cases & assumptions

- Bucket names are unique across the two endpoints; on a collision the registry
  keeps the reachable / last-probed endpoint.
- Reachability is **never** cached across launches (VPN state changes); only the
  bucket → endpoint map is. The probe re-runs each launch.
- Probe failure: connect/timeout → network-unreachable; auth/other error →
  surfaced in the status bar, endpoint treated as unusable for routing.

## Constitution check

- §4 — probe + all S3 I/O run on worker threads; UI via `call_from_thread`.
- §5 — every new function fully type-annotated.
- §6 — registry entries are small dataclasses, not Pydantic.
- §9 — `buckets.json` stores only bucket → endpoint; never credentials.
- §7/§10 — no new daemon; mount workers untouched.

## Out of scope

- Changing the mount backend or sync engine internals.
- Cross-endpoint bucket migration / copying a campus bucket to web.
- Caching object listings.

## Test plan

- `bucket_registry`: merge keeps unreachable entries, drops deleted reachable
  ones, round-trips through disk, `entries()` annotates reachability.
- `s3_router`: routes by bucket, raises `EndpointUnreachable` for unreachable /
  unknown buckets, `create_bucket` registers, `list_buckets` returns the union,
  probe merges (Minio + socket mocked).
- TUI: existing `test_tui.py` updated — the `e`-switch tests are replaced with a
  `NetworkBar` presence/initial-render test; navigation tests patch
  `router.list_buckets`.
