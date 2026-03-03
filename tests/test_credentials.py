"""Tests for secure credential storage."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uw_s3.credentials import (
    ENCRYPTED_CREDS_FILE,
    SERVICE_NAME,
    CredentialManager,
    migrate_from_env,
)


@pytest.fixture
def temp_config_dir(monkeypatch, tmp_path):
    """Use temporary directory for config."""
    config_dir = tmp_path / ".config" / "uw-s3"
    config_dir.mkdir(parents=True)

    # Patch the CONFIG_DIR and ENCRYPTED_CREDS_FILE in the module
    import uw_s3.credentials as creds_module
    monkeypatch.setattr(creds_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(creds_module, "ENCRYPTED_CREDS_FILE", config_dir / "credentials.enc")

    return config_dir


@pytest.fixture
def mock_keyring_unavailable(monkeypatch):
    """Mock keyring as unavailable to test encrypted file fallback."""
    def mock_get_password(*args, **kwargs):
        raise RuntimeError("Keyring unavailable")

    monkeypatch.setattr("keyring.get_password", mock_get_password)
    return True


class TestCredentialManagerKeyring:
    """Tests for keyring-based credential storage."""

    def test_store_and_load_credentials(self, temp_config_dir):
        """Test storing and loading credentials via keyring."""
        manager = CredentialManager()

        # Skip if keyring is not available
        if not manager._use_keyring:
            pytest.skip("Keyring not available in test environment")

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

        if not manager._use_keyring:
            pytest.skip("Keyring not available in test environment")

        assert not manager.has_credentials()

        manager.store_credentials("test_access", "test_secret", "web")
        assert manager.has_credentials()

        # Cleanup
        manager.delete_credentials()

    def test_delete_credentials(self, temp_config_dir):
        """Test deleting stored credentials."""
        manager = CredentialManager()

        if not manager._use_keyring:
            pytest.skip("Keyring not available in test environment")

        manager.store_credentials("test_access", "test_secret", "campus")
        assert manager.has_credentials()

        manager.delete_credentials()
        assert not manager.has_credentials()


class TestCredentialManagerEncrypted:
    """Tests for encrypted file-based credential storage."""

    def test_store_and_load_encrypted(self, temp_config_dir, mock_keyring_unavailable):
        """Test storing and loading credentials via encrypted file."""
        manager = CredentialManager()

        # Ensure we're using encrypted file
        assert not manager._use_keyring
        assert manager.storage_method == "encrypted-file"

        manager.store_credentials("test_access_enc", "test_secret_enc", "web")

        # Verify file was created with correct permissions
        creds_file = temp_config_dir / "credentials.enc"
        assert creds_file.exists()

        # Load and verify
        access, secret, endpoint = manager.load_credentials()
        assert access == "test_access_enc"
        assert secret == "test_secret_enc"
        assert endpoint == "web"

    def test_encrypted_file_permissions(self, temp_config_dir, mock_keyring_unavailable):
        """Test that encrypted file has correct permissions."""
        manager = CredentialManager()
        manager.store_credentials("test_access", "test_secret", "campus")

        creds_file = temp_config_dir / "credentials.enc"
        stat_info = creds_file.stat()
        mode = stat_info.st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_load_nonexistent_encrypted(self, temp_config_dir, mock_keyring_unavailable):
        """Test loading when no encrypted file exists."""
        manager = CredentialManager()

        with pytest.raises(ValueError, match="not found"):
            manager.load_credentials()

    def test_encrypted_decryption_different_machine(
        self, temp_config_dir, mock_keyring_unavailable, monkeypatch
    ):
        """Test that encrypted credentials are machine-specific."""
        manager = CredentialManager()
        manager.store_credentials("test_access", "test_secret", "campus")

        # Simulate different machine by changing hostname
        monkeypatch.setenv("USER", "different_user")

        # Create a new manager instance (will derive different key)
        manager2 = CredentialManager()

        # Should fail to decrypt with different key
        with pytest.raises(ValueError, match="Failed to decrypt"):
            manager2.load_credentials()

    def test_has_credentials_encrypted(self, temp_config_dir, mock_keyring_unavailable):
        """Test has_credentials with encrypted storage."""
        manager = CredentialManager()

        assert not manager.has_credentials()

        manager.store_credentials("test_access", "test_secret", "campus")
        assert manager.has_credentials()

        manager.delete_credentials()
        assert not manager.has_credentials()


class TestCredentialMigration:
    """Tests for migrating from .env to secure storage."""

    def test_migrate_from_env(self, temp_config_dir, mock_keyring_unavailable):
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

    def test_migrate_no_env_file(self, temp_config_dir, mock_keyring_unavailable):
        """Test migration when no .env file exists."""
        result = migrate_from_env()
        assert result is False

    def test_migrate_invalid_env(self, temp_config_dir, mock_keyring_unavailable):
        """Test migration with invalid .env file."""
        env_file = temp_config_dir / ".env"
        env_file.write_text("INVALID=content\n")

        result = migrate_from_env()
        assert result is False


class TestCredentialManagerStorageMethod:
    """Tests for storage method detection."""

    def test_storage_method_keyring(self, temp_config_dir):
        """Test storage method reports keyring when available."""
        manager = CredentialManager()

        if manager._use_keyring:
            assert manager.storage_method == "keyring"
        else:
            pytest.skip("Keyring not available")

    def test_storage_method_encrypted(self, temp_config_dir, mock_keyring_unavailable):
        """Test storage method reports encrypted-file when keyring unavailable."""
        manager = CredentialManager()
        assert manager.storage_method == "encrypted-file"
