"""CLI entry point — loads credentials and launches the TUI."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT
from uw_s3.preferences import load_preferences
from uw_s3.tui.app import UWS3App
from uw_s3.updater import check_and_update

CONFIG_DIR = Path.home() / ".config" / "uw-s3"


def _resolve_endpoint() -> str:
    saved = load_preferences().get("endpoint")
    if saved in (CAMPUS_ENDPOINT, WEB_ENDPOINT):
        return saved
    env = os.getenv("S3_ENDPOINT", "campus").lower()
    return WEB_ENDPOINT if env == "web" else CAMPUS_ENDPOINT


def main() -> None:
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

    check_and_update()

    app = UWS3App(
        access_key=access_key,
        secret_key=secret_key,
        endpoint=_resolve_endpoint(),
    )
    app.run()
