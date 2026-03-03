# Security Improvements for Credential Storage

## Overview

This document outlines the security improvements implemented to address credential storage vulnerabilities in uw-s3.

## Problems Addressed

### 1. Plain Text Credential Storage
**Previous:** Credentials stored in `~/.config/uw-s3/.env` in plain text
- Anyone with file system access could read credentials
- Only protected by file permissions (chmod 600)
- Vulnerable if system is compromised

**Solution:** Hybrid secure storage system
- **Primary:** System keyring (OS-native secure storage)
- **Fallback:** Encrypted file with machine-specific key derivation

### 2. Visible Credentials During Setup
**Previous:** Access key visible during terminal input
- Secret key used `stty -echo`, but access key was plaintext
- Could be captured by screen recording or shoulder surfing

**Solution:** Both keys now use hidden input
- Access key: `stty -echo` before input
- Secret key: `stty -echo` before input (maintained)
- No credentials visible on screen during installation

### 3. rclone Configuration Security
**Previous:** Temporary config files contained plaintext credentials
**Status:** Already secure with 0o600 permissions (verified, no changes needed)

## Implementation Details

### Credential Manager (`src/uw_s3/credentials.py`)

#### Storage Methods

**1. System Keyring (Primary)**
- Uses Python `keyring` library
- Platform-specific backends:
  - **macOS:** Keychain
  - **Linux:** Secret Service API (GNOME Keyring, KWallet)
  - **Windows:** Credential Locker
- Credentials encrypted by OS at rest
- Integrated with system authentication

**2. Encrypted File (Fallback)**
- Used when keyring is unavailable (headless servers, containers)
- Location: `~/.config/uw-s3/credentials.enc`
- Encryption: Fernet (symmetric encryption from cryptography library)
- Key derivation:
  - Algorithm: PBKDF2-HMAC-SHA256
  - Iterations: 100,000
  - Salt: Derived from `username@hostname`
  - Machine-specific: Cannot be decrypted on different machine
- File permissions: 0o600 (owner read/write only)

#### Security Properties

1. **Confidentiality:** Credentials encrypted at rest
2. **Integrity:** Fernet includes authentication
3. **Machine-binding:** Encrypted credentials tied to specific machine
4. **Access control:** File permissions + OS keyring permissions
5. **Forward compatibility:** Graceful fallback when keyring unavailable

### CLI Integration (`src/uw_s3/cli.py`)

**Automatic Migration Flow:**
1. Check if credentials exist in secure storage
2. If not, attempt migration from `.env` file
3. If `.env` found, migrate and backup original
4. If no `.env`, check environment variables
5. If env vars found, store in secure storage
6. Load credentials from secure storage

**Backward Compatibility:**
- Environment variables still supported
- Automatically migrated on first run
- Original `.env` backed up as `.env.backup`

### Installation Script (`scripts/install.sh`)

**Security Enhancements:**
1. Hidden input for both access and secret keys
2. Direct integration with CredentialManager
3. Automatic detection of storage method
4. User notification of which method is being used

**Installation Flow:**
```bash
# Both credentials now hidden
printf "Access Key ID: "
stty -echo
read -r access_key
stty echo
echo

printf "Secret Access Key: "
stty -echo
read -r secret_key
stty echo
echo

# Store using Python credential manager
python3 <<EOF
from uw_s3.credentials import CredentialManager
manager = CredentialManager()
manager.store_credentials(access_key, secret_key, endpoint)
print(f"Stored using {manager.storage_method}")
EOF
```

### Migration Utility (`scripts/migrate_credentials.py`)

**Purpose:** Manual migration tool for existing users

**Features:**
- Interactive confirmation before overwriting
- Automatic detection of existing credentials
- Progress reporting
- Safety backup of original `.env`

**Usage:**
```bash
uv run python scripts/migrate_credentials.py
```

## Testing

Comprehensive test suite in `tests/test_credentials.py`:

### Test Coverage
1. **Keyring Storage**
   - Store and retrieve credentials
   - Credential existence check
   - Credential deletion

2. **Encrypted File Storage**
   - Encryption and decryption
   - File permissions verification
   - Machine-specific encryption
   - Invalid file handling

3. **Migration**
   - Successful migration from `.env`
   - Missing `.env` handling
   - Invalid `.env` handling

4. **Storage Method Detection**
   - Keyring availability detection
   - Fallback to encrypted file

### Running Tests
```bash
uv run pytest tests/test_credentials.py -v
```

## Security Considerations

### Threat Model

**Protected Against:**
1. ✅ Casual file system access (plain text storage)
2. ✅ Screen recording/shoulder surfing during setup
3. ✅ Accidental credential exposure in backups
4. ✅ Credential theft via file copying (machine-bound encryption)

**NOT Protected Against:**
1. ❌ Root/Administrator access (OS keyring access)
2. ❌ Memory dumps while application running
3. ❌ Malicious code with user privileges
4. ❌ Physical access with system unlock (by design)

### Best Practices

1. **Use System Keyring When Possible**
   - More secure than encrypted file
   - OS-level protection mechanisms
   - Better integration with system security

2. **Encrypted File for Headless Systems**
   - Acceptable trade-off for environments without keyring
   - Machine-bound encryption prevents simple copying
   - Better than plain text `.env`

3. **Regular Credential Rotation**
   - Change credentials periodically
   - Delete old credentials: `manager.delete_credentials()`
   - Re-run installer or use API to update

4. **Access Control**
   - Maintain restrictive file permissions
   - Limit user account access
   - Monitor for unauthorized access attempts

## Migration Guide for Users

### For New Users
Simply run the installer:
```bash
curl -LsSf https://raw.githubusercontent.com/jasonlo/uw-s3/main/scripts/install.sh | sh
```

### For Existing Users
Credentials will be automatically migrated on first run after upgrade:
```bash
# Update the tool
uv tool upgrade uw-s3

# Run - will auto-migrate
uw-s3
```

Manual migration (optional):
```bash
uv run python scripts/migrate_credentials.py
```

### Verification
Check which storage method is being used:
```python
from uw_s3.credentials import CredentialManager
manager = CredentialManager()
print(f"Storage method: {manager.storage_method}")
print(f"Has credentials: {manager.has_credentials()}")
```

## Future Enhancements

Potential improvements for consideration:

1. **Hardware Security Module (HSM) Support**
   - YubiKey integration
   - TPM-based encryption
   - Biometric authentication

2. **Credential Rotation**
   - Automated credential refresh
   - Expiration warnings
   - API-driven updates

3. **Audit Logging**
   - Credential access logging
   - Failed authentication tracking
   - Security event monitoring

4. **Multi-Factor Authentication**
   - TOTP support
   - Push notifications
   - Biometric confirmation

5. **Secret Sharing**
   - Team credential management
   - Role-based access control
   - Centralized secret storage

## References

- [Python keyring library](https://github.com/jaraco/keyring)
- [cryptography library](https://cryptography.io/)
- [PBKDF2 specification](https://tools.ietf.org/html/rfc2898)
- [Fernet specification](https://github.com/fernet/spec)

## Support

For issues or questions:
- GitHub Issues: https://github.com/jasonlo/uw-s3/issues
- Email: lcmjlo@gmail.com
