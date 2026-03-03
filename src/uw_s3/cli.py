"""CLI entry point — loads credentials and launches the TUI."""

import atexit
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

from uw_s3.credentials import CredentialManager, migrate_from_env

CONFIG_DIR = Path.home() / ".config" / "uw-s3"


def main() -> None:
    # Handle --check-credentials flag for installer
    if len(sys.argv) > 1 and sys.argv[1] == "--check-credentials":
        manager = CredentialManager()
        sys.exit(0 if manager.has_credentials() else 1)

    manager = CredentialManager()

    # Try to migrate from old .env file
    if not manager.has_credentials():
        if migrate_from_env():
            print(
                "Migrated credentials from .env to system keyring.",
                file=sys.stderr,
            )
        else:
            # Fallback to environment variables or .env for backward compatibility
            load_dotenv()
            load_dotenv(CONFIG_DIR / ".env")

            access_key = os.getenv("S3_ACCESS_KEY_ID", "")
            secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "")
            endpoint_env = os.getenv("S3_ENDPOINT", "campus").lower()

            if not access_key or not secret_key:
                print(
                    "Error: No credentials found.\n"
                    "Run the installer or set S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY.",
                    file=sys.stderr,
                )
                sys.exit(1)

            # Store credentials from env vars for future use
            endpoint_typed = "web" if endpoint_env == "web" else "campus"
            manager.store_credentials(access_key, secret_key, endpoint_typed)
            print(
                "Stored credentials in system keyring.",
                file=sys.stderr,
            )

    # Load credentials from secure storage
    try:
        access_key, secret_key, endpoint_type = manager.load_credentials()
    except ValueError as e:
        print(f"Error loading credentials: {e}", file=sys.stderr)
        sys.exit(1)

    from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT
    from uw_s3.tui.app import UWS3App

    endpoint = WEB_ENDPOINT if endpoint_type == "web" else CAMPUS_ENDPOINT

    app = UWS3App(access_key=access_key, secret_key=secret_key, endpoint=endpoint)

    atexit.register(app.on_unmount)

    def _signal_handler(signum: int, _frame: object) -> None:
        app.on_unmount()
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGHUP, _signal_handler)

    app.run()
