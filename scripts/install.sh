#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="$HOME/.local/bin"
TARGET="$TARGET_DIR/gemini"

mkdir -p "$TARGET_DIR"
cp "$REPO_ROOT/gemini_cli.py" "$TARGET"
chmod +x "$TARGET"

grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"

echo "Installed to $TARGET"
echo "Run: source ~/.bashrc && hash -r"
