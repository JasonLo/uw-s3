# uw-s3

Terminal UI for UW-Madison Research Object Storage (S3). Wraps the MinIO Python client in a [Textual](https://textual.textualize.io/) TUI for syncing folders to/from S3 buckets and mounting buckets as local directories via rclone FUSE.

## Install

Requires Python >= 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync          # install dependencies
uv run uw-s3     # launch the TUI
```

For mounting buckets, [rclone](https://rclone.org/install/) must be on your PATH.

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```
S3_ACCESS_KEY_ID=your_key
S3_SECRET_ACCESS_KEY=your_secret
S3_ENDPOINT=campus  # "campus" (UW network/VPN, default) or "web" (any network)
```

## Usage

The main menu provides three modes:

- **Manage Buckets** — create, delete, and set permissions on S3 buckets
- **Manage Files** — browse buckets, upload/download individual files, and bulk-sync folders
- **Mount Bucket** — mount a bucket as a local directory via rclone FUSE

The endpoint (campus vs web) can be toggled at runtime from the main menu.

## Development

```bash
uv run pytest            # run tests
uv run ruff check .      # lint
uv run ruff format .     # format
```

## Docs

- <https://kb.wisc.edu/researchdata/134019>
- <https://kb.wisc.edu/researchdata/134396>
