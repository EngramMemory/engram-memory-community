# Engram — OpenClaw Integration Guide

## How It Works

Engram integrates with OpenClaw as a native plugin. The plugin registers memory tools and lifecycle hooks that give your agent persistent memory across sessions.

| File | Purpose |
|---|---|
| `openclaw.plugin.json` | Plugin manifest — tells OpenClaw what tools exist |
| `plugin.py` | Plugin entry point — dispatches tool calls to memory scripts |
| `src/index.ts` | TypeScript plugin — implements lifecycle hooks, tool handlers, category detection |

## Tools Registered

| Tool | Description |
|---|---|
| `memory_store` | Store text with semantic embedding and auto-classification |
| `memory_search` | Search stored memories using semantic similarity |

## Lifecycle Hooks

- **`before_agent_start`** — searches Qdrant with the user's message, injects relevant memories as `<recalled_memories>` context
- **`after_agent_response`** — extracts facts from the conversation and auto-stores them

## Configuration

Add to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "allow": ["engram"],
    "slots": {
      "memory": "engram"
    },
    "entries": {
      "engram": {
        "enabled": true,
        "config": {
          "qdrantUrl": "http://localhost:6333",
          "embeddingUrl": "http://localhost:11435",
          "collection": "agent-memory",
          "autoRecall": true,
          "autoCapture": true,
          "debug": false
        }
      }
    }
  }
}
```

For multi-machine setups, replace `localhost` with the IPs of your Qdrant and FastEmbed hosts.

## Verifying It Works

```bash
# 1. Check Qdrant is reachable
curl http://localhost:6333/health

# 2. Check FastEmbed is reachable
curl http://localhost:11435/health

# 3. Check plugin loaded
openclaw status | grep engram

# 4. Test in an OpenClaw chat:
# memory_store "Testing Engram integration" --category fact
# memory_search "testing"

# 5. Enable debug mode to see hook activity:
# Set "debug": true in config, then:
openclaw gateway logs --follow | grep engram
```
