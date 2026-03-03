#!/usr/bin/env python3
"""Migrate credentials from .env to secure storage."""

import sys
from pathlib import Path

# Add the src directory to the path for development
src_dir = Path(__file__).parent.parent / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

from uw_s3.credentials import CredentialManager, migrate_from_env


def main() -> None:
    manager = CredentialManager()

    print("=== uw-s3 Credential Migration ===")
    print()

    if manager.has_credentials():
        print("Credentials already exist in system keyring.")
        response = input("Overwrite with credentials from .env? (y/N): ").strip().lower()
        if response != "y":
            print("Migration cancelled.")
            return

        manager.delete_credentials()

    print("Migrating credentials from .env file...")
    if migrate_from_env():
        print("✓ Successfully migrated credentials to system keyring.")
        print()
        print("The old .env file has been renamed to .env.backup for safety.")
        print("You can delete it once you've verified the migration works.")
    else:
        print("✗ No .env file found or credentials are invalid.")
        print()
        print("Run the installer to set up credentials.")
        sys.exit(1)


if __name__ == "__main__":
    main()
