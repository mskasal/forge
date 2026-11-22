#!/bin/sh
# Install Forge on macOS or Linux (safe to re-run):
#   1. Create Python virtual environment (.venv) and install core + Hub dependencies
#   2. Symlink `forge` CLI into ~/.local/bin/forge
#   3. Link the open-standard Forge skill for Claude, Gemini/Antigravity, .agents, and Codex
#   4. Run `forge doctor`
set -eu
cd "$(dirname "$0")"
REPO=$(pwd)

PY=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3 || true)
if [ -z "$PY" ]; then
  echo "✗ Python 3.11+ not found. Install Python 3.11+ and re-run ./install.sh."
  exit 1
fi

echo "1/4 Python environment & packages..."
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[hub,dev]"
if [ "${FORGE_WITH_APPLETV:-0}" = "1" ]; then
  .venv/bin/pip install -q -e ".[appletv]" || echo "   ! usd-core optional install skipped"
fi

echo "2/4 forge CLI..."
mkdir -p "$HOME/.local/bin"
ln -sfn "$REPO/.venv/bin/forge" "$HOME/.local/bin/forge"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "   ! Add ~/.local/bin to your PATH: export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

echo "3/4 Agent skills (Claude, Gemini/Antigravity, Open Standard, Codex)..."
for target in \
  "$HOME/.claude/skills" \
  "$HOME/.gemini/config/skills" \
  "$HOME/.agents/skills" \
  "$HOME/.codex/skills"; do
  mkdir -p "$target"
  ln -sfn "$REPO/skills/forge" "$target/forge"
  echo "   linked: $target/forge"
done

echo "4/4 Diagnostics..."
echo
exec .venv/bin/forge doctor
