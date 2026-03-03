"""Secure credential storage using system keyring with encrypted file fallback."""

import base64
import json
import os
from pathlib import Path
from typing import Literal

import keyring
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

CONFIG_DIR = Path.home() / ".config" / "uw-s3"
ENCRYPTED_CREDS_FILE = CONFIG_DIR / "credentials.enc"
SERVICE_NAME = "uw-s3"

EndpointType = Literal["campus", "web"]


class CredentialManager:
    """Manage S3 credentials using keyring or encrypted file fallback."""

    def __init__(self) -> None:
        self._use_keyring = self._check_keyring_available()

    def _check_keyring_available(self) -> bool:
        """Check if system keyring is available and functional."""
        try:
            # Try to use keyring with a test operation
            keyring.get_password(SERVICE_NAME, "_test_")
            return True
        except (RuntimeError, keyring.errors.KeyringError):
            return False

    def _get_encryption_key(self) -> bytes:
        """Derive encryption key from machine-specific data."""
        # Use hostname + username as salt source for machine-specific encryption
        import socket

        username = os.getenv("USER", os.getenv("USERNAME", "default"))
        hostname = socket.gethostname()
        salt_source = f"{username}@{hostname}".encode()

        # Derive a key using PBKDF2
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt_source,
            iterations=100_000,
        )
        # Use a fixed password combined with salt to derive key
        key = base64.urlsafe_b64encode(kdf.derive(b"uw-s3-credential-key"))
        return key

    def store_credentials(
        self,
        access_key: str,
        secret_key: str,
        endpoint: EndpointType = "campus",
    ) -> None:
        """Store credentials securely using keyring or encrypted file."""
        if self._use_keyring:
            self._store_in_keyring(access_key, secret_key, endpoint)
        else:
            self._store_encrypted(access_key, secret_key, endpoint)

    def _store_in_keyring(
        self, access_key: str, secret_key: str, endpoint: EndpointType
    ) -> None:
        """Store credentials in system keyring."""
        keyring.set_password(SERVICE_NAME, "access_key", access_key)
        keyring.set_password(SERVICE_NAME, "secret_key", secret_key)
        keyring.set_password(SERVICE_NAME, "endpoint", endpoint)

    def _store_encrypted(
        self, access_key: str, secret_key: str, endpoint: EndpointType
    ) -> None:
        """Store credentials in encrypted file as fallback."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        key = self._get_encryption_key()
        fernet = Fernet(key)

        data = {
            "access_key": access_key,
            "secret_key": secret_key,
            "endpoint": endpoint,
        }

        encrypted = fernet.encrypt(json.dumps(data).encode())

        # Write with restrictive permissions
        ENCRYPTED_CREDS_FILE.touch(mode=0o600, exist_ok=True)
        ENCRYPTED_CREDS_FILE.write_bytes(encrypted)

    def load_credentials(self) -> tuple[str, str, EndpointType]:
        """Load credentials from keyring or encrypted file.

        Returns:
            Tuple of (access_key, secret_key, endpoint)

        Raises:
            ValueError: If credentials are not found or invalid
        """
        if self._use_keyring:
            return self._load_from_keyring()
        else:
            return self._load_encrypted()

    def _load_from_keyring(self) -> tuple[str, str, EndpointType]:
        """Load credentials from system keyring."""
        access_key = keyring.get_password(SERVICE_NAME, "access_key")
        secret_key = keyring.get_password(SERVICE_NAME, "secret_key")
        endpoint = keyring.get_password(SERVICE_NAME, "endpoint")

        if not access_key or not secret_key:
            raise ValueError("Credentials not found in keyring")

        endpoint_typed: EndpointType = (
            "web" if endpoint == "web" else "campus"
        )
        return access_key, secret_key, endpoint_typed

    def _load_encrypted(self) -> tuple[str, str, EndpointType]:
        """Load credentials from encrypted file."""
        if not ENCRYPTED_CREDS_FILE.exists():
            raise ValueError(f"Encrypted credentials file not found: {ENCRYPTED_CREDS_FILE}")

        key = self._get_encryption_key()
        fernet = Fernet(key)

        try:
            encrypted = ENCRYPTED_CREDS_FILE.read_bytes()
            decrypted = fernet.decrypt(encrypted)
            data = json.loads(decrypted.decode())

            access_key = data.get("access_key", "")
            secret_key = data.get("secret_key", "")
            endpoint = data.get("endpoint", "campus")

            if not access_key or not secret_key:
                raise ValueError("Invalid credential data")

            endpoint_typed: EndpointType = (
                "web" if endpoint == "web" else "campus"
            )
            return access_key, secret_key, endpoint_typed
        except Exception as e:
            raise ValueError(f"Failed to decrypt credentials: {e}") from e

    def has_credentials(self) -> bool:
        """Check if credentials are stored."""
        try:
            self.load_credentials()
            return True
        except ValueError:
            return False

    def delete_credentials(self) -> None:
        """Delete stored credentials."""
        if self._use_keyring:
            try:
                keyring.delete_password(SERVICE_NAME, "access_key")
                keyring.delete_password(SERVICE_NAME, "secret_key")
                keyring.delete_password(SERVICE_NAME, "endpoint")
            except keyring.errors.PasswordDeleteError:
                pass
        else:
            ENCRYPTED_CREDS_FILE.unlink(missing_ok=True)

    @property
    def storage_method(self) -> str:
        """Return the storage method being used."""
        return "keyring" if self._use_keyring else "encrypted-file"


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
