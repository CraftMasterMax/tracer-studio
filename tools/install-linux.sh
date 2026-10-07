#!/usr/bin/env bash
# Install Tracer Studio for the current user (Linux).  Idempotent —
# re-run any time, in particular after moving the repo (paths rewrite).
#
#   * venv + editable package   -> the `tracer` entry point exists
#   * ~/.local/bin/tracer       -> one easy command, anywhere
#   * launcher entry + icon     -> "Tracer Studio" in the app grid
#   * *.tracer file association -> double-click a document to open it
#
# Uninstall: tools/uninstall-linux.sh (repo and venv survive both).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 1. python environment (TRACER_PYTHON=... to choose the interpreter)
PY="${TRACER_PYTHON:-python3}"
[ -x "$ROOT/.venv/bin/python" ] || "$PY" -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --quiet --upgrade pip
"$ROOT/.venv/bin/python" -m pip install --quiet -e "$ROOT"

# 2. the one easy command
mkdir -p "$HOME/.local/bin"
ln -sf "$ROOT/.venv/bin/tracer" "$HOME/.local/bin/tracer"

# 3. launcher entry, icon, MIME association (all user-scoped, no sudo)
DIR="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/256x256/apps"
MIME="$HOME/.local/share/mime"
mkdir -p "$DIR" "$ICONS" "$MIME/packages"
sed "s|@PREFIX@|$ROOT|" "$ROOT/packaging/linux/tracer-studio.desktop" \
    > "$DIR/tracer-studio.desktop"
cp "$ROOT/tracer/resources/tracer.png" "$ICONS/tracer-studio.png"
cp "$ROOT/packaging/linux/tracer-studio.xml" "$MIME/packages/tracer-studio.xml"
command -v update-desktop-database >/dev/null \
    && update-desktop-database "$DIR" || true
command -v update-mime-database >/dev/null \
    && update-mime-database "$MIME" || true
# after the db updates: be the chosen app for our own extension
command -v xdg-mime >/dev/null \
    && xdg-mime default tracer-studio.desktop application/x-tracer || true
command -v gtk-update-icon-cache >/dev/null \
    && gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" || true

echo
echo "Tracer Studio installed."
echo "  command      : tracer                 (tracer file.tracer opens it)"
echo "  launcher     : 'Tracer Studio' in the app grid / launcher search"
echo "  double-click : .tracer files open Tracer"
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "  NOTE: add ~/.local/bin to PATH for the 'tracer' command." ;;
esac
