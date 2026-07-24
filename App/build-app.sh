#!/usr/bin/env bash
#
# Build CleanScan.app from the Swift Package (no Xcode required).
#
#   ./build-app.sh [debug|release]
#
# Assembles a proper .app bundle (Info.plist + ad-hoc signature) so notifications
# and file access behave. The app locates the Python backend via BackendLocator:
# in this dev layout it finds the sibling ../Backend automatically, so the venv
# does NOT need to be copied into the bundle (a venv can't be relocated cleanly;
# distribution would require embedding a relocatable Python — out of scope here).
#
set -euo pipefail
cd "$(dirname "$0")"                 # App/
APP_NAME="CleanScan"
CONFIG="${1:-release}"

echo "==> swift build -c $CONFIG"
swift build -c "$CONFIG"
BIN_DIR="$(swift build -c "$CONFIG" --show-bin-path)"
BIN="$BIN_DIR/$APP_NAME"
[ -x "$BIN" ] || { echo "build failed: $BIN not found" >&2; exit 1; }

APP_DIR="$PWD/$APP_NAME.app"
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"
cp "$BIN" "$APP_DIR/Contents/MacOS/$APP_NAME"
cp Info.plist.template "$APP_DIR/Contents/Info.plist"

# App icon (generate once with: Resources/make_icon.py).
if [ -f "$PWD/../Resources/AppIcon.icns" ]; then
  cp "$PWD/../Resources/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns"
fi

# Bundle fonts (used by the renderer for guaranteed umlaut coverage).
if [ -d "$PWD/../Resources/fonts" ]; then
  mkdir -p "$APP_DIR/Contents/Resources/Resources"
  rsync -a "$PWD/../Resources/fonts" "$APP_DIR/Contents/Resources/Resources/" 2>/dev/null || true
fi

# Ad-hoc signature (identity "-"): enough for local notifications + Gatekeeper run.
codesign --force --deep --sign - "$APP_DIR" 2>/dev/null \
  || echo "[warn] ad-hoc codesign failed; the app still runs but notifications may be limited"

echo "==> Built $APP_DIR"
echo "    open \"$APP_DIR\""
