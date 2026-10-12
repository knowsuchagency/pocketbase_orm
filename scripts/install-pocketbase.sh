#!/usr/bin/env bash
set -euo pipefail

# 1. Prepare install directory inside project
INSTALL_DIR="$(pwd)/db"
mkdir -p "$INSTALL_DIR"

DOWNLOAD_URL="https://github.com/pocketbase/pocketbase/releases/download/v0.28.0/pocketbase_0.28.0_linux_amd64.zip"
TMPDIR="$(mktemp -d)"

FILE_NAME="pocketbase_0.28.0_linux_amd64.zip"
echo "⬇️  Downloading"
curl -L "$DOWNLOAD_URL" -o "${TMPDIR}/${FILE_NAME}"

# 5. Unzip and install
echo "📦 Unpacking..."
unzip -q "${TMPDIR}/${FILE_NAME}" -d "${TMPDIR}"
chmod +x "${TMPDIR}/pocketbase"
mv "${TMPDIR}/pocketbase" "${INSTALL_DIR}/pocketbase"

# 6. Cleanup
rm -rf "$TMPDIR"

echo "✅ PocketBase installed to ${INSTALL_DIR}/pocketbase"
echo "👉 Run it with: ./db/pocketbase serve --dir ./pb_data --http 127.0.0.1:8090"
