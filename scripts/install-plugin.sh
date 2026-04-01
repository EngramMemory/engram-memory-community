#!/bin/bash
# Install Engram as the OpenClaw memory plugin
# Usage: bash scripts/install-plugin.sh

set -e

PLUGIN_DIR="$HOME/.openclaw/extensions/engram"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Find openclaw binary
export PATH="$HOME/.npm-global/bin:$HOME/.local/bin:/usr/local/bin:$PATH"
OPENCLAW=$(command -v openclaw 2>/dev/null || echo "")

echo "=== Installing Engram Memory Plugin ==="

# Copy plugin files
mkdir -p "$PLUGIN_DIR"
cp "$SCRIPT_DIR/plugin/index.js" "$PLUGIN_DIR/"
cp "$SCRIPT_DIR/plugin/package.json" "$PLUGIN_DIR/"
cp "$SCRIPT_DIR/plugin/openclaw.plugin.json" "$PLUGIN_DIR/"

echo "  Plugin files installed to $PLUGIN_DIR"

# Configure — local-only mode (no API key needed)
if [ -n "$OPENCLAW" ]; then
  $OPENCLAW config set "plugins.entries.engram" '{"enabled":true,"config":{"qdrantUrl":"http://localhost:6333","autoCapture":true,"autoRecall":true}}'
  $OPENCLAW config set "plugins.slots.memory" "engram"
  echo "  Memory slot set to Engram (local mode)"
else
  echo "  WARNING: openclaw not found in PATH. Configure manually — see README."
fi

echo ""
echo "=== Done ==="
echo ""
echo "Engram is running in local mode (your Qdrant, no cloud)."
echo "To connect to Engram Cloud for overflow, compression, and analytics:"
echo "  1. Get an API key at https://app.engrammemory.ai"
echo "  2. Add it to your OpenClaw config:"
echo "     openclaw config set \"plugins.entries.engram.config.apiKey\" \"eng_live_YOUR_KEY\""
echo ""
echo "Restart OpenClaw to apply: openclaw gateway restart"
