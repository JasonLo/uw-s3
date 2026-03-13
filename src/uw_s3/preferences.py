"""Persist user preferences to ~/.config/uw-s3/preferences.json."""

import json
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "uw-s3"
PREFS_FILE = CONFIG_DIR / "preferences.json"


def load_preferences() -> dict[str, Any]:
    """Load saved preferences, returning empty dict if none exist."""
    if not PREFS_FILE.exists():
        return {}
    try:
        return json.loads(PREFS_FILE.read_text())
    except json.JSONDecodeError, OSError:
        return {}


def save_preferences(prefs: dict[str, Any]) -> None:
    """Save preferences to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    PREFS_FILE.write_text(json.dumps(prefs, indent=2))


def update_preference(key: str, value: Any) -> None:
    """Update a single preference key."""
    prefs = load_preferences()
    prefs[key] = value
    save_preferences(prefs)
