#!/bin/bash
# Install Engram as the OpenClaw memory plugin
# Usage: bash scripts/install-plugin.sh [API_KEY] [QDRANT_URL]

set -e

API_KEY="${1:-}"
QDRANT_URL="${2:-http://localhost:6333}"
PLUGIN_DIR="$HOME/.openclaw/extensions/engram"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Installing Engram Memory Plugin ==="

# Copy plugin files
mkdir -p "$PLUGIN_DIR"
cp "$SCRIPT_DIR/plugin/index.js" "$PLUGIN_DIR/"
cp "$SCRIPT_DIR/plugin/package.json" "$PLUGIN_DIR/"
cp "$SCRIPT_DIR/plugin/openclaw.plugin.json" "$PLUGIN_DIR/"

echo "  Plugin files installed to $PLUGIN_DIR"

# Configure if API key provided
if [ -n "$API_KEY" ]; then
  echo "  Configuring with API key ${API_KEY:0:16}..."
  openclaw config set "plugins.entries.engram" "{\"enabled\":true,\"config\":{\"apiKey\":\"$API_KEY\",\"qdrantUrl\":\"$QDRANT_URL\",\"autoCapture\":true,\"autoRecall\":true}}"
  openclaw config set "plugins.slots.memory" "engram"
  echo "  Memory slot set to Engram"
else
  echo ""
  echo "  To activate, run:"
  echo "    openclaw config set \"plugins.entries.engram\" '{\"enabled\":true,\"config\":{\"apiKey\":\"YOUR_KEY\",\"qdrantUrl\":\"$QDRANT_URL\",\"autoCapture\":true,\"autoRecall\":true}}'"
  echo "    openclaw config set \"plugins.slots.memory\" \"engram\""
fi

echo ""
echo "=== Done ==="
echo "Restart OpenClaw to apply: openclaw gateway restart"
