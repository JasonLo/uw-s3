"""CLI entry point — loads credentials and launches the TUI."""

import atexit
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

CONFIG_DIR = Path.home() / ".config" / "uw-s3"


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

    from uw_s3.updater import check_and_update

    check_and_update()

    from uw_s3 import CAMPUS_ENDPOINT, WEB_ENDPOINT
    from uw_s3.preferences import load_preferences
    from uw_s3.tui.app import UWS3App

    prefs = load_preferences()
    saved_endpoint = prefs.get("endpoint")
    if saved_endpoint in (CAMPUS_ENDPOINT, WEB_ENDPOINT):
        endpoint = saved_endpoint
    else:
        endpoint_env = os.getenv("S3_ENDPOINT", "campus").lower()
        endpoint = WEB_ENDPOINT if endpoint_env == "web" else CAMPUS_ENDPOINT

    app = UWS3App(access_key=access_key, secret_key=secret_key, endpoint=endpoint)

    atexit.register(app.on_unmount)

    def _signal_handler(signum: int, _frame: object) -> None:
        app.on_unmount()
        sys.exit(128 + signum)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGHUP, _signal_handler)

    app.run()
