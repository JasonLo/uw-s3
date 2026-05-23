#!/usr/bin/env bash
# Evaluate s3fs-fuse against a uw-s3 bucket on the chosen endpoint.
# Usage: ./try_s3fs_fuse.sh <bucket> [campus|web]
# Credentials are read from S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY
# (never written to disk). Mount stays foregrounded; Ctrl-C unmounts.

set -euo pipefail

BUCKET="${1:?usage: $0 <bucket> [campus|web]}"
ENDPOINT_KEY="${2:-campus}"

case "$ENDPOINT_KEY" in
  campus) ENDPOINT="campus.s3.wisc.edu" ;;
  web)    ENDPOINT="web.s3.wisc.edu" ;;
  *) echo "endpoint must be 'campus' or 'web'" >&2; exit 2 ;;
esac

: "${S3_ACCESS_KEY_ID:?set S3_ACCESS_KEY_ID}"
: "${S3_SECRET_ACCESS_KEY:?set S3_SECRET_ACCESS_KEY}"

if ! command -v s3fs >/dev/null 2>&1; then
  echo "s3fs not on PATH; install s3fs-fuse first" >&2
  exit 2
fi

MNT="$(mktemp -d -t s3fs-eval-XXXX)"

cleanup() {
  echo
  echo "Unmounting $MNT ..."
  fusermount -u "$MNT" 2>/dev/null || true
  rmdir "$MNT" 2>/dev/null || true
  echo "Orphans (s3fs): $(pgrep -fa s3fs || echo none)"
  echo "Orphans (rclone): $(pgrep -fa rclone || echo none)"
}
trap cleanup EXIT INT TERM

echo "Mount point: $MNT"
echo "Endpoint:    https://$ENDPOINT"
echo "Bucket:      $BUCKET"
echo

t0=$(date +%s.%N)
AWS_ACCESS_KEY_ID="$S3_ACCESS_KEY_ID" \
AWS_SECRET_ACCESS_KEY="$S3_SECRET_ACCESS_KEY" \
s3fs "$BUCKET" "$MNT" \
  -o url="https://$ENDPOINT" \
  -o use_path_request_style \
  -o stat_cache_expire=1 \
  -f &
MOUNT_PID=$!

for _ in $(seq 1 100); do
  if mountpoint -q "$MNT" 2>/dev/null; then break; fi
  if ! kill -0 "$MOUNT_PID" 2>/dev/null; then
    echo "s3fs exited before mount was ready" >&2
    exit 1
  fi
  sleep 0.1
done
t1=$(date +%s.%N)

if ! mountpoint -q "$MNT" 2>/dev/null; then
  echo "Mount never came up within 10s" >&2
  kill "$MOUNT_PID" 2>/dev/null || true
  exit 1
fi

LATENCY=$(awk -v t0="$t0" -v t1="$t1" 'BEGIN{printf "%.2f", t1-t0}')
echo "Mount established in ${LATENCY}s (target: <=3s)"
echo
echo "Top-level listing (first 10 entries):"
ls -la "$MNT" 2>&1 | head -11
echo
echo "Mount staying up; press Ctrl-C to unmount."
wait "$MOUNT_PID"
