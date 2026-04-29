"""Auto-update checker — compares installed version against latest GitHub tag."""

import json
import os
import re
import shutil
import subprocess
import urllib.request

from uw_s3 import __version__


REPO_URL = "https://github.com/jasonlo/uw-s3.git"
TAGS_API = "https://api.github.com/repos/jasonlo/uw-s3/tags"
USER_AGENT = f"uw-s3/{__version__}"

_SKIP_UPDATE_ENV = "UW_S3_JUST_UPDATED"
_DISABLE_UPDATE_ENV = "UW_S3_NO_AUTO_UPDATE"
_VERSION_RE = re.compile(r"^\d+(\.\d+)*$")


def get_current_version() -> str:
    """Return the installed version of uw-s3."""
    return __version__


def get_latest_version() -> str | None:
    """Fetch the latest tag from GitHub, returning version string or None on failure."""
    try:
        req = urllib.request.Request(
            TAGS_API,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            tags: list[dict[str, str]] = json.loads(resp.read())
        if not tags:
            return None
        return tags[0]["name"].lstrip("v")
    except Exception:
        return None


def _parse_version(v: str) -> tuple[int, ...] | None:
    """Parse '1.2.3' into (1, 2, 3). Returns None for non-numeric versions."""
    if not _VERSION_RE.match(v):
        return None
    return tuple(int(x) for x in v.split("."))


def _is_newer(latest: str, current: str) -> bool:
    """Return True iff latest > current, padding tuples to the same length."""
    a = _parse_version(latest)
    b = _parse_version(current)
    if a is None or b is None:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def check_and_update() -> None:
    """Check for updates and optionally reinstall."""
    if os.environ.pop(_SKIP_UPDATE_ENV, None):
        return
    if os.environ.get(_DISABLE_UPDATE_ENV):
        return

    current = get_current_version()
    latest = get_latest_version()
    if latest is None or not _is_newer(latest, current):
        return

    print(f"Update available: v{current} → v{latest}")
    answer = input("Update now? (y/N) ").strip().lower()
    if answer != "y":
        return

    result = subprocess.run(
        ["uv", "tool", "install", "--force", f"git+{REPO_URL}", "--python", "3.14"],
        check=False,
    )
    if result.returncode != 0:
        print("Update failed.")
        return

    exe = shutil.which("uws3")
    if exe:
        print(f"Updated to v{latest}. Restarting...")
        os.environ[_SKIP_UPDATE_ENV] = "1"
        os.execvp(exe, [exe])
