# Quick Start Guide

Get Engram running in under 5 minutes.

## Prerequisites

- Docker
- Python 3.10+
- 4GB+ RAM

## Step 1: Install

```bash
# OpenClaw
clawhub install engrammemory

# Or clone directly
git clone https://github.com/EngramMemory/engram-memory.git
cd engram-memory
```

## Step 2: Setup

```bash
bash scripts/setup.sh
```

This starts the single all-in-one `engram-memory` container (Qdrant + FastEmbed + the MCP server bundled together), installs context system dependencies, and registers the MCP server with Claude Code via `claude mcp add engrammemory -s user --transport http http://localhost:8585/mcp`. The MCP server listens on port 8585 at the `/mcp` endpoint. setup.sh also writes an OpenClaw config file (`openclaw-memory-config.json`) for OpenClaw users.

## Step 3: Configure (OpenClaw users)

If you use OpenClaw, add the generated config from `openclaw-memory-config.json` to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "entries": {
      "engram": {
        "enabled": true,
        "config": {
          "qdrantUrl": "http://localhost:6333",
          "embeddingUrl": "http://localhost:11435",
          "autoRecall": true,
          "autoCapture": true
        }
      }
    }
  }
}
```

Restart the gateway: `openclaw gateway restart`

## Step 4: Test

```bash
# Store a memory
memory_store "I prefer TypeScript over JavaScript" --category preference

# Search memories
memory_search "programming language preferences"

# Ask about your project (after initializing context)
engram-context init . --template web-app
context_ask "How does authentication work?"
```

## Step 5: Add SOUL Rules (Optional)

See `docs/SOUL-RULES.md` for recommended rules that teach your agent to use memory proactively. Adapt what fits your style.

## Verify

```bash
# Check Qdrant
curl http://localhost:6333/collections

# Check FastEmbed
curl http://localhost:11435/health
```

## Troubleshooting

**Port conflicts:**
```bash
sudo lsof -i :6333
sudo lsof -i :11435
```

**Docker issues:**
```bash
docker restart engram-memory
```

**Memory tools not available:**
1. Verify plugin config in `~/.openclaw/openclaw.json`
2. Check `openclaw status` for plugin errors
3. Ensure the container is running: `docker ps --filter name=engram-memory`

## Next Steps

- [Architecture Overview](ARCHITECTURE.md)
- [Context System](../context/README.md)
- [SOUL Rules](SOUL-RULES.md)
- When ready to scale: [Engram Cloud](ENGRAM_CLOUD.md)
