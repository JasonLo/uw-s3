#!/bin/bash
set -euo pipefail

REPO="git+https://github.com/JasonLo/uw-s3.git"
CONFIG_DIR="$HOME/.config/uw-s3"
ENV_FILE="$CONFIG_DIR/.env"

echo "=== uw-s3 installer ==="
echo

# Install uw-s3 as a uv tool
echo "Installing uw-s3..."
uv tool install "$REPO" --python 3.14
echo

# Set up credentials
if [ -f "$ENV_FILE" ]; then
    echo "Credentials already configured at $ENV_FILE"
else
    echo "Enter your UW Research Object Storage credentials."
    echo "(Get them from https://storage.researchdata.wisc.edu)"
    echo
    read -rp "S3_ACCESS_KEY_ID: " access_key
    read -rsp "S3_SECRET_ACCESS_KEY: " secret_key
    echo
    read -rp "S3_ENDPOINT (campus/web) [campus]: " endpoint
    endpoint=${endpoint:-campus}

    mkdir -p "$CONFIG_DIR"
    cat > "$ENV_FILE" <<EOF
S3_ACCESS_KEY_ID=$access_key
S3_SECRET_ACCESS_KEY=$secret_key
S3_ENDPOINT=$endpoint
EOF
    chmod 600 "$ENV_FILE"
    echo "Credentials saved to $ENV_FILE"
fi
echo

# Optional: install rclone for mount support
if command -v rclone &>/dev/null; then
    echo "rclone found: $(rclone version --check | head -1 2>/dev/null || rclone --version | head -1)"
else
    read -rp "Install rclone for mount support? (y/N): " install_rclone
    if [[ "$install_rclone" =~ ^[Yy]$ ]]; then
        sudo -v && curl https://rclone.org/install.sh | sudo bash
    else
        echo "Skipping rclone (mount feature will be unavailable)."
    fi
fi
echo

echo "Done! Run 'uw-s3' to start."
