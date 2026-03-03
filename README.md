# uw-s3

Terminal UI for UW-Madison Research Object Storage (S3). Wraps the MinIO Python client in a [Textual](https://textual.textualize.io/) TUI for syncing folders to/from S3 buckets and mounting buckets as local directories via rclone FUSE.

## Install

Requires [uv](https://docs.astral.sh/uv/).

```bash
curl -LsSf https://raw.githubusercontent.com/jasonlo/uw-s3/main/scripts/install.sh | sh
```

The installer will set up `uw-s3`, securely prompt for your S3 credentials, and optionally install rclone for mount support.

**Security:** Credentials are stored securely using your system's native keyring (macOS Keychain, Linux Secret Service, Windows Credential Locker). Both access key and secret key input are hidden during installation.

Once installed, run from anywhere:

```bash
uw-s3
```

### Manual install

```bash
uv tool install git+https://github.com/jasonlo/uw-s3.git --python 3.14
```

Then run the installer to set up credentials, or manually configure them:

```bash
# Via installer (recommended)
curl -LsSf https://raw.githubusercontent.com/jasonlo/uw-s3/main/scripts/install.sh | sh

# Or manually store credentials
python3 -c "from uw_s3.credentials import CredentialManager; CredentialManager().store_credentials('your_access_key', 'your_secret_key', 'campus')"
```

For mounting buckets, [rclone](https://rclone.org/install/) must be on your PATH.

### Migrating from older versions

If you have an existing `.env` file from a previous version, credentials will be automatically migrated to secure storage on first run. You can also manually migrate:

```bash
uv run python scripts/migrate_credentials.py
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

## Reference

- [S3 Getting Started](https://kb.wisc.edu/researchdata/134019)
- [Bucket Creation & Configuration](https://kb.wisc.edu/researchdata/134396)
