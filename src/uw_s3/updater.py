"""Auto-update checker — compares installed version against latest GitHub tag."""

import importlib.metadata
import json
import subprocess
import sys
import urllib.request


REPO_URL = "https://github.com/jasonlo/uw-s3.git"
TAGS_API = "https://api.github.com/repos/jasonlo/uw-s3/tags"


def get_current_version() -> str:
    """Return the installed version of uw-s3."""
    return importlib.metadata.version("uw-s3")


def get_latest_version() -> str | None:
    """Fetch the latest tag from GitHub, returning version string or None on failure."""
    try:
        req = urllib.request.Request(
            TAGS_API, headers={"Accept": "application/vnd.github.v3+json"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            tags: list[dict[str, str]] = json.loads(resp.read())
        if not tags:
            return None
        return tags[0]["name"].lstrip("v")
    except Exception:
        return None


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string like '0.1.0' into a comparable tuple."""
    return tuple(int(x) for x in v.split("."))


def check_and_update() -> None:
    """Check for updates and optionally reinstall."""
    current = get_current_version()
    latest = get_latest_version()
    if latest is None:
        return

    try:
        if _parse_version(latest) <= _parse_version(current):
            return
    except ValueError, TypeError:
        return

    print(f"Update available: v{current} → v{latest}")
    answer = input("Update now? (y/N) ").strip().lower()
    if answer != "y":
        return

    subprocess.run(
        ["uv", "tool", "install", "--force", f"git+{REPO_URL}", "--python", "3.14"],
        check=False,
    )
    print("Restart uw-s3 to use the new version.")
    sys.exit(0)
