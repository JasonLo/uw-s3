"""Secure credential storage using system keyring."""

import os
from pathlib import Path
from typing import Literal

import keyring

CONFIG_DIR = Path.home() / ".config" / "uw-s3"
SERVICE_NAME = "uw-s3"

EndpointType = Literal["campus", "web"]


class CredentialManager:
    """Manage S3 credentials using system keyring."""

    def store_credentials(
        self,
        access_key: str,
        secret_key: str,
        endpoint: EndpointType = "campus",
    ) -> None:
        """Store credentials securely in system keyring."""
        keyring.set_password(SERVICE_NAME, "access_key", access_key)
        keyring.set_password(SERVICE_NAME, "secret_key", secret_key)
        keyring.set_password(SERVICE_NAME, "endpoint", endpoint)

    def load_credentials(self) -> tuple[str, str, EndpointType]:
        """Load credentials from system keyring.

        Returns:
            Tuple of (access_key, secret_key, endpoint)

        Raises:
            ValueError: If credentials are not found or invalid
        """
        access_key = keyring.get_password(SERVICE_NAME, "access_key")
        secret_key = keyring.get_password(SERVICE_NAME, "secret_key")
        endpoint = keyring.get_password(SERVICE_NAME, "endpoint")

        if not access_key or not secret_key:
            raise ValueError("Credentials not found in keyring")

        endpoint_typed: EndpointType = "web" if endpoint == "web" else "campus"
        return access_key, secret_key, endpoint_typed

    def has_credentials(self) -> bool:
        """Check if credentials are stored."""
        try:
            self.load_credentials()
            return True
        except ValueError:
            return False

    def delete_credentials(self) -> None:
        """Delete stored credentials."""
        try:
            keyring.delete_password(SERVICE_NAME, "access_key")
            keyring.delete_password(SERVICE_NAME, "secret_key")
            keyring.delete_password(SERVICE_NAME, "endpoint")
        except keyring.errors.PasswordDeleteError:
            pass


def migrate_from_env() -> bool:
    """Migrate credentials from .env file to secure storage.

    Returns:
        True if migration was performed, False if no .env found
    """
    from dotenv import load_dotenv

    env_file = CONFIG_DIR / ".env"
    if not env_file.exists():
        return False

    load_dotenv(env_file)
    access_key = os.getenv("S3_ACCESS_KEY_ID", "")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY", "")
    endpoint_str = os.getenv("S3_ENDPOINT", "campus").lower()
    endpoint: EndpointType = "web" if endpoint_str == "web" else "campus"

    if not access_key or not secret_key:
        return False

    manager = CredentialManager()
    manager.store_credentials(access_key, secret_key, endpoint)

    # Backup the old .env file before removing
    backup_file = CONFIG_DIR / ".env.backup"
    env_file.rename(backup_file)

    return True
