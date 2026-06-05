"""CLI entry point — launches the TUI or runs a headless backup/restore."""

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv
from minio.error import S3Error

from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT, UWS3
from uw_s3.backup_ops import BackupResult, parse_s3_uri, run_backup, run_restore
from uw_s3.preferences import load_preferences
from uw_s3.tui.app import UWS3App
from uw_s3.updater import check_and_update

CONFIG_DIR = Path.home() / ".config" / "uw-s3"


def _resolve_endpoint(override: str | None = None) -> str:
    if override:
        return WEB_ENDPOINT if override.lower() == "web" else CAMPUS_ENDPOINT
    saved = load_preferences().get("endpoint")
    if saved in (CAMPUS_ENDPOINT, WEB_ENDPOINT):
        return saved
    env = os.getenv("S3_ENDPOINT", "campus").lower()
    return WEB_ENDPOINT if env == "web" else CAMPUS_ENDPOINT


def _load_credentials() -> tuple[str, str]:
    """Load S3 credentials from .env/environment, exiting 1 if missing."""
    load_dotenv()
    load_dotenv(CONFIG_DIR / ".env")
    access_key = os.getenv("S3_ACCESS_KEY_ID", "")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "")
    if not access_key or not secret_key:
        print(
            "Error: S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be set "
            "(in .env or environment).",
            file=sys.stderr,
        )
        sys.exit(1)
    return access_key, secret_key


def _fmt_bytes(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _emit_result(
    result: BackupResult, verb: str, *, as_json: bool, quiet: bool
) -> None:
    if as_json:
        print(json.dumps(asdict(result)))
        return
    if quiet:
        return
    prefix = f"would {verb}" if result.dry_run else f"{verb}ed"
    print(
        f"{prefix} {result.transferred} files ({_fmt_bytes(result.bytes)}), "
        f"{result.skipped} skipped"
    )


def _add_common_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--endpoint", choices=["campus", "web"], default=None)
    p.add_argument(
        "--json", action="store_true", dest="as_json", help="Machine-readable output."
    )
    p.add_argument("--quiet", action="store_true", help="Suppress non-error output.")
    p.add_argument(
        "--dry-run", action="store_true", dest="dry_run", help="Preview only."
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="uws3", description="UW-Madison S3 storage — TUI and CLI."
    )
    sub = parser.add_subparsers(dest="command")

    backup = sub.add_parser("backup", help="Upload a file or folder to S3.")
    backup.add_argument("local_path", help="Local file or directory to upload.")
    backup.add_argument("remote", metavar="s3://bucket/key", help="Destination URI.")
    _add_common_flags(backup)

    restore = sub.add_parser("restore", help="Download a file or folder from S3.")
    restore.add_argument("remote", metavar="s3://bucket/key", help="Source URI.")
    restore.add_argument("local_path", help="Local destination file or directory.")
    _add_common_flags(restore)

    return parser


def _run_command(args: argparse.Namespace) -> int:
    access_key, secret_key = _load_credentials()
    endpoint = _resolve_endpoint(args.endpoint)
    client = UWS3(access_key, secret_key, endpoint=endpoint)
    on_file = None if (args.quiet or args.as_json) else (lambda p: print(f"  {p}"))
    try:
        bucket, key = parse_s3_uri(args.remote)
        if args.command == "backup":
            result = run_backup(
                client,
                Path(args.local_path),
                bucket,
                key,
                endpoint=endpoint,
                dry_run=args.dry_run,
                on_file=on_file,
            )
            verb = "push"
        else:
            result = run_restore(
                client,
                bucket,
                key,
                Path(args.local_path),
                endpoint=endpoint,
                dry_run=args.dry_run,
                on_file=on_file,
            )
            verb = "pull"
    except (ValueError, FileNotFoundError, S3Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    _emit_result(result, verb, as_json=args.as_json, quiet=args.quiet)
    return 0


def _run_tui() -> None:
    access_key, secret_key = _load_credentials()
    check_and_update()
    app = UWS3App(
        access_key=access_key,
        secret_key=secret_key,
        endpoint=_resolve_endpoint(),
    )
    app.run()


def main() -> None:
    args = _build_parser().parse_args()
    if args.command is None:
        _run_tui()
        return
    sys.exit(_run_command(args))
