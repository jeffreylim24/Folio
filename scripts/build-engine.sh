#!/usr/bin/env bash
# Build the Python engine into a single-file sidecar binary for Tauri.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TRIPLE="$(rustc -vV | sed -n 's/host: //p')"
EXT=""
case "$TRIPLE" in *windows*) EXT=".exe" ;; esac

cd "$ROOT/engine"
uv run pyinstaller --onefile --noconfirm --name folio-engine \
  --copy-metadata folio-engine \
  --collect-submodules uvicorn \
  --collect-submodules folio_engine \
  --collect-submodules keyring \
  pyinstaller_entry.py

mkdir -p "$ROOT/app/src-tauri/binaries"
cp "dist/folio-engine$EXT" "$ROOT/app/src-tauri/binaries/folio-engine-$TRIPLE$EXT"
echo "Built app/src-tauri/binaries/folio-engine-$TRIPLE$EXT"
