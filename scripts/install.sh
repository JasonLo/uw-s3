#!/bin/sh
set -eu

REPO="git+https://github.com/jasonlo/uw-s3.git"
CONFIG_DIR="$HOME/.config/uw-s3"

echo "=== uw-s3 installer ==="
echo

# Install uw-s3 as a uv tool
echo "Installing uw-s3..."
uv tool install "$REPO" --python 3.14
echo

# Check if credentials already exist
if uv tool run uw-s3 --check-credentials 2>/dev/null; then
    echo "Credentials already configured."
    printf "Overwrite? (y/N): "
    read -r overwrite < /dev/tty
    case "$overwrite" in
        [Yy]) ;;
        *)
            echo "Keeping existing credentials."
            echo
            echo "Done! Run 'uw-s3' to start."
            exit 0
            ;;
    esac
fi

echo "Enter your UW Research Object Storage credentials."
echo "Get them from https://storage.researchdata.wisc.edu"
echo

while true; do
    printf "Access Key ID: "
    stty -echo < /dev/tty
    read -r access_key < /dev/tty
    stty echo < /dev/tty
    echo
    [ -n "$access_key" ] && break
    echo "Access key cannot be empty."
done

while true; do
    printf "Secret Access Key: "
    stty -echo < /dev/tty
    read -r secret_key < /dev/tty
    stty echo < /dev/tty
    echo
    [ -n "$secret_key" ] && break
    echo "Secret key cannot be empty."
done

echo "Endpoint:"
echo "  campus — faster, but requires UW network or VPN (will hang otherwise)"
echo "  web    — works from any network"
printf "Choose endpoint [campus]: "
read -r endpoint < /dev/tty
endpoint=${endpoint:-campus}

# Store credentials using Python script
python3 <<EOF
import sys
sys.path.insert(0, "$HOME/.local/share/uv/tools/uw-s3/lib/python*/site-packages")
from uw_s3.credentials import CredentialManager

manager = CredentialManager()
manager.store_credentials(
    access_key="$access_key",
    secret_key="$secret_key",
    endpoint="$endpoint"
)
print("\nCredentials stored securely in system keyring.")
EOF

echo

# Optional: install rclone for mount support
if command -v rclone >/dev/null 2>&1; then
    echo "rclone found (mount support available)."
else
    printf "Install rclone for mount support? (y/N): "
    read -r install_rclone < /dev/tty
    case "$install_rclone" in
        [Yy]) sudo -v && curl https://rclone.org/install.sh | sudo bash ;;
        *) echo "Skipping rclone (mount feature will be unavailable)." ;;
    esac
fi

echo
echo "Done! Run 'uw-s3' to start."
