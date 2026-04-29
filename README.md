# uw-s3

Terminal UI for UW-Madison Research Object Storage (S3). Wraps the MinIO Python client in a [Textual](https://textual.textualize.io/) TUI for syncing folders to/from S3 buckets and mounting buckets as local directories via rclone FUSE.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
curl -LsSf https://raw.githubusercontent.com/jasonlo/uw-s3/main/scripts/install.sh | sh
```

The installer will set up `uws3`, prompt for your S3 credentials, and optionally install rclone for mount support.

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
S3_ENDPOINT=campus  # "campus" (UW network/VPN, default) or "web" (any network)
```

For mounting buckets, [rclone](https://rclone.org/install/) must be on your PATH.

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

## Reference

- [S3 Getting Started](https://kb.wisc.edu/researchdata/134019)
- [Bucket Creation & Configuration](https://kb.wisc.edu/researchdata/134396)
