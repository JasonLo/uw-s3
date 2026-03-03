"""Tests for secure credential storage."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uw_s3.credentials import (
    SERVICE_NAME,
    CredentialManager,
    migrate_from_env,
)


@pytest.fixture
def temp_config_dir(monkeypatch, tmp_path):
    """Use temporary directory for config."""
    config_dir = tmp_path / ".config" / "uw-s3"
    config_dir.mkdir(parents=True)

    # Patch the CONFIG_DIR in the module
    import uw_s3.credentials as creds_module
    monkeypatch.setattr(creds_module, "CONFIG_DIR", config_dir)

    return config_dir


class TestCredentialManagerKeyring:
    """Tests for keyring-based credential storage."""

    def test_store_and_load_credentials(self, temp_config_dir):
        """Test storing and loading credentials via keyring."""
        manager = CredentialManager()

        manager.store_credentials("test_access", "test_secret", "campus")

        access, secret, endpoint = manager.load_credentials()
        assert access == "test_access"
        assert secret == "test_secret"
        assert endpoint == "campus"

        # Cleanup
        manager.delete_credentials()

    def test_has_credentials(self, temp_config_dir):
        """Test checking if credentials exist."""
        manager = CredentialManager()

        assert not manager.has_credentials()

        manager.store_credentials("test_access", "test_secret", "web")
        assert manager.has_credentials()

        # Cleanup
        manager.delete_credentials()

    def test_delete_credentials(self, temp_config_dir):
        """Test deleting stored credentials."""
        manager = CredentialManager()

        manager.store_credentials("test_access", "test_secret", "campus")
        assert manager.has_credentials()

        manager.delete_credentials()
        assert not manager.has_credentials()

    def test_load_nonexistent_credentials(self, temp_config_dir):
        """Test loading when no credentials exist."""
        manager = CredentialManager()

        with pytest.raises(ValueError, match="not found in keyring"):
            manager.load_credentials()


class TestCredentialMigration:
    """Tests for migrating from .env to secure storage."""

    def test_migrate_from_env(self, temp_config_dir):
        """Test migrating credentials from .env file."""
        # Create a .env file
        env_file = temp_config_dir / ".env"
        env_file.write_text(
            "S3_ACCESS_KEY_ID=migrated_access\n"
            "S3_SECRET_ACCESS_KEY=migrated_secret\n"
            "S3_ENDPOINT=web\n"
        )

        # Perform migration
        result = migrate_from_env()
        assert result is True

        # Verify credentials were migrated
        manager = CredentialManager()
        access, secret, endpoint = manager.load_credentials()
        assert access == "migrated_access"
        assert secret == "migrated_secret"
        assert endpoint == "web"

        # Verify .env was backed up
        assert not env_file.exists()
        backup_file = temp_config_dir / ".env.backup"
        assert backup_file.exists()

        # Cleanup
        manager.delete_credentials()

    def test_migrate_no_env_file(self, temp_config_dir):
        """Test migration when no .env file exists."""
        result = migrate_from_env()
        assert result is False

    def test_migrate_invalid_env(self, temp_config_dir):
        """Test migration with invalid .env file."""
        env_file = temp_config_dir / ".env"
        env_file.write_text("INVALID=content\n")

        result = migrate_from_env()
        assert result is False
