#!/usr/bin/env bash
# Undo tools/install-linux.sh (user-scoped files only; repo + venv stay).
set -euo pipefail
rm -f "$HOME/.local/bin/tracer" \
      "$HOME/.local/share/applications/tracer-studio.desktop" \
      "$HOME/.local/share/icons/hicolor/256x256/apps/tracer-studio.png" \
      "$HOME/.local/share/mime/packages/tracer-studio.xml"
command -v update-desktop-database >/dev/null \
    && update-desktop-database "$HOME/.local/share/applications" || true
command -v update-mime-database >/dev/null \
    && update-mime-database "$HOME/.local/share/mime" || true
echo "Removed. The repo and its .venv were left untouched."
