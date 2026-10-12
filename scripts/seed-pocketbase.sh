#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${PB_DATA_DIR:-./db/pb_data}"
BIN="${PB_BIN:-./db/pocketbase}"

# ─── PRE-CHECKS ────────────────────────────────────────────────

# Don’t overwrite existing data
if [ -d "$DATA_DIR" ]; then
  echo "Error: data directory '$DATA_DIR' already exists."
  echo "       Please remove it or set PB_DATA_DIR to a new location."
  exit 1
fi

# Ensure admin credentials are set
if [ -z "${ADMIN_EMAIL:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
  echo "Error: both ADMIN_EMAIL and ADMIN_PASSWORD must be set in the environment."
  exit 1
fi

# ─── PREPARE & SEED ────────────────────────────────────────────

echo "Creating data directory at '$DATA_DIR'..."
mkdir -p "$DATA_DIR"

echo "Seeding superuser (email=$ADMIN_EMAIL)..."
"$BIN" superuser create \
  "$ADMIN_EMAIL" \
  "$ADMIN_PASSWORD" \
  --dir "$DATA_DIR"

echo "Done."
