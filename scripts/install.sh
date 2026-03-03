#!/bin/sh
set -eu

REPO="git+https://github.com/jasonlo/uw-s3.git"
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
    printf "Overwrite? (y/N): "
    read -r overwrite
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
    read -r access_key
    [ -n "$access_key" ] && break
    echo "Access key cannot be empty."
done

while true; do
    printf "Secret Access Key: "
    stty -echo
    read -r secret_key
    stty echo
    echo
    [ -n "$secret_key" ] && break
    echo "Secret key cannot be empty."
done

printf "Endpoint — campus (UW VPN) or web (any network) [campus]: "
read -r endpoint
endpoint=${endpoint:-campus}

mkdir -p "$CONFIG_DIR"
cat > "$ENV_FILE" <<EOF
S3_ACCESS_KEY_ID=$access_key
S3_SECRET_ACCESS_KEY=$secret_key
S3_ENDPOINT=$endpoint
EOF
chmod 600 "$ENV_FILE"
echo
echo "Credentials saved to $ENV_FILE"

# Optional: install rclone for mount support
echo
if command -v rclone >/dev/null 2>&1; then
    echo "rclone found (mount support available)."
else
    printf "Install rclone for mount support? (y/N): "
    read -r install_rclone
    case "$install_rclone" in
        [Yy]) sudo -v && curl https://rclone.org/install.sh | sudo bash ;;
        *) echo "Skipping rclone (mount feature will be unavailable)." ;;
    esac
fi

echo
echo "Done! Run 'uw-s3' to start."
