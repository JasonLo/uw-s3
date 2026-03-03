"""Persist sync mappings to ~/.config/uw-s3/sync.json."""

import json
from dataclasses import asdict
from pathlib import Path

from uw_s3.sync.models import SyncMap

CONFIG_DIR = Path.home() / ".config" / "uw-s3"
CONFIG_FILE = CONFIG_DIR / "sync.json"


def load_mappings() -> list[SyncMap]:
    """Load all saved sync mappings."""
    if not CONFIG_FILE.exists():
        return []
    data = json.loads(CONFIG_FILE.read_text())
    return [SyncMap(**entry) for entry in data]


def save_mappings(mappings: list[SyncMap]) -> None:
    """Save sync mappings to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps([asdict(m) for m in mappings], indent=2))


def add_mapping(mapping: SyncMap) -> None:
    """Add a new sync mapping (replaces if same id exists)."""
    mappings = [m for m in load_mappings() if m.id != mapping.id]
    mappings.append(mapping)
    save_mappings(mappings)


def remove_mapping(mapping_id: str) -> None:
    """Remove a sync mapping by id."""
    mappings = [m for m in load_mappings() if m.id != mapping_id]
    save_mappings(mappings)
