# uw-s3

Terminal UI for UW-Madison Research Object Storage (S3). Wraps the MinIO Python client in a [Textual](https://textual.textualize.io/) TUI for syncing folders to/from S3 buckets and mounting buckets as local directories via FUSE (in-process Python [`s3fs`](https://s3fs.readthedocs.io/)).

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
curl -LsSf https://raw.githubusercontent.com/jasonlo/uw-s3/main/scripts/install.sh | sh
```

The installer will set up `uws3` and prompt for your S3 credentials. Mount support uses in-process Python `s3fs` and ships with the app — no extra binary install.

Once installed, run from anywhere:

```bash
uws3
```

### Manual install

```bash
uv tool install git+https://github.com/jasonlo/uw-s3.git --python 3.14
```

Then create `~/.config/uw-s3/.env` with your credentials:

```
S3_ACCESS_KEY_ID=your_key
S3_SECRET_ACCESS_KEY=your_secret
```

You no longer pick an endpoint. UW buckets live on one of two domains —
`campus.s3.wisc.edu` (UW network/VPN only) or `web.s3.wisc.edu` (public) — and
the app detects which domains it can reach, probes both for your buckets, and
remembers which bucket lives where so every operation routes automatically.

Mounting requires FUSE on the host (`fuse3` on Linux/WSL2, macFUSE on macOS). The `s3fs` and `fsspec[fuse]` Python deps install via `uv sync`.

## Usage

The main menu provides three modes:

- **Manage Buckets** — create, delete, and set permissions on S3 buckets
- **Manage Files** — browse buckets, upload/download individual files, and bulk-sync folders
- **Mount Bucket** — mount a bucket as a local directory via FUSE (Python `s3fs`)

A status bar shows which domains are reachable. Buckets on an unreachable domain
(e.g. campus buckets while you're off-VPN) are listed greyed-out with a hint;
connect to the UW network and hit **Refresh** to use them. The only place you
choose a domain is when **creating** a bucket, where it's an inherent choice.

## Development

```bash
uv run pytest            # run tests
uv run ruff check .      # lint
uv run ruff format .     # format
```

## Reference

- [S3 Getting Started](https://kb.wisc.edu/researchdata/134019)
- [Bucket Creation & Configuration](https://kb.wisc.edu/researchdata/134396)
