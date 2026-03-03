"""CLI entry point — loads credentials and launches the TUI."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()

    access_key = os.getenv("S3_ACCESS_KEY_ID", "")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "")

    if not access_key or not secret_key:
        print(
            "Error: S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY must be set "
            "(in .env or environment).",
            file=sys.stderr,
        )
        sys.exit(1)

    from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT
    from uw_s3.tui.app import UWS3App

    endpoint_env = os.getenv("S3_ENDPOINT", "campus").lower()
    endpoint = WEB_ENDPOINT if endpoint_env == "web" else CAMPUS_ENDPOINT

    app = UWS3App(access_key=access_key, secret_key=secret_key, endpoint=endpoint)
    app.run()
