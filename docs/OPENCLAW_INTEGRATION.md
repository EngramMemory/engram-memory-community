# Perfect Recall — OpenClaw Integration Guide

## What Changed

Your repo had the memory architecture right (Qdrant + FastEmbed + OpenClaw) but was missing the plugin glue code that OpenClaw needs to actually load and use it. These new files close that gap:

| File | Purpose |
|---|---|
| `openclaw.plugin.json` | Plugin manifest — tells OpenClaw what tools/hooks exist and what config options are available |
| `src/index.ts` | Plugin entry point — implements the `register()` function, lifecycle hooks, tool handlers, dedup, and decay |
| `package.json` | NPM package definition for build/install |
| `tsconfig.json` | TypeScript build config |

## New Capabilities Added

### 1. Deduplication
Before storing any memory, the plugin embeds the text and searches Qdrant for matches above `dedupThreshold` (default 0.92). If a near-duplicate exists, it skips storage and bumps the existing memory's access count instead. This prevents the "same fact stored 50 times" problem.

### 2. Memory Decay
Every 50 messages, the plugin checks if it's time for a decay pass (configurable via `decayIntervalDays`, default 30). Memories that haven't been accessed since the last decay interval get their importance multiplied by `decayFactor` (0.95). When importance drops below `decayFloor` (0.1), the memory is pruned. Frequently accessed memories stay fresh.

### 3. Access Tracking
Every time a memory is returned from search (auto-recall or manual), its `accessCount` and `lastAccessed` fields are updated. This feeds the decay system — useful memories survive, forgotten ones fade.

### 4. Auto-Classification
If no category is provided, the plugin detects it from the text content using keyword patterns (prefer/like → preference, decided/chosen → decision, etc.).

### 5. Proper Hook Integration
- `before_agent_start` — queries Qdrant with the user's message, injects relevant memories as `<recalled_memories>` prepended context
- `after_agent_response` — extracts facts from the conversation turn and auto-stores them (with dedup)

## Build & Install

```bash
# From the repo root
cd perfect_recall

# Install dependencies
npm install

# Build TypeScript → JavaScript
npm run build

# Copy to OpenClaw extensions directory
sudo cp -r . ~/.openclaw/workspace/skills/perfect-recall/
# OR for system-wide:
# sudo cp -r . /usr/lib/node_modules/openclaw/extensions/perfect-recall/

# Restart gateway
openclaw gateway restart
```

## Multi-Machine Configuration (Three-Brain Setup)

If Qdrant runs on a different machine than OpenClaw, update the URLs in your `openclaw.json`:

```json
{
  "plugins": {
    "allow": ["perfect-recall"],
    "slots": {
      "memory": "perfect-recall"
    },
    "entries": {
      "perfect-recall": {
        "enabled": true,
        "config": {
          "qdrantUrl": "http://QDRANT_MACHINE_IP:6333",
          "embeddingUrl": "http://FASTEMBED_MACHINE_IP:11435",
          "collection": "agent-memory",
          "autoRecall": true,
          "autoCapture": true,
          "dedupThreshold": 0.92,
          "decayEnabled": true,
          "debug": true
        }
      }
    }
  }
}
```

Replace `QDRANT_MACHINE_IP` and `FASTEMBED_MACHINE_IP` with the actual IPs of those machines in your network. Make sure ports 6333 and 11435 are accessible between the machines (firewall rules, etc.).

## Verifying It Works

```bash
# 1. Check Qdrant is reachable
curl http://QDRANT_IP:6333/health

# 2. Check FastEmbed is reachable
curl http://FASTEMBED_IP:11435/health

# 3. Check plugin loaded
openclaw status | grep perfect-recall

# 4. Test memory store manually
# In an OpenClaw chat:
# memory_store "Testing perfect recall integration" --category fact

# 5. Test recall
# memory_search "testing"

# 6. Enable debug mode to see hook activity in logs
# Set "debug": true in config, then watch:
openclaw gateway logs --follow | grep perfect-recall
```

## Repo Structure After Integration

```
perfect_recall/
├── openclaw.plugin.json    ← NEW: Plugin manifest
├── src/
│   └── index.ts            ← NEW: Plugin entry point
├── dist/                   ← NEW: Built JS output (after npm run build)
├── package.json            ← NEW: NPM package
├── tsconfig.json           ← NEW: TypeScript config
├── bin/                    ← KEEP: CLI wrappers still useful
├── config/                 ← KEEP: Docker compose, etc.
├── context/                ← KEEP: Context system
├── docs/                   ← KEEP: Documentation
├── scripts/                ← KEEP: Setup scripts
├── SKILL.md                ← KEEP: Update to reflect new plugin structure
├── README.md               ← KEEP: Update to reflect new plugin structure
└── LICENSE                 ← KEEP
```

## What's Still Not Wired (Future Work)

1. **Context system → Qdrant bridge**: The `.context/` file system isn't yet feeding into the vector store. You'd want a script that embeds context files and stores them in a separate Qdrant collection (e.g., `project-context`) so `perfect-recall-ask` can do unified semantic search across both memory and codebase context.

2. **Memory consolidation**: Decay handles pruning, but you could add a nightly job that finds clusters of related memories (similarity 0.7-0.9) and merges them into summary memories. This is what EverMemOS calls "memory lifecycle management."

3. **Profile stored in Qdrant**: Currently profile data is just memories with category "preference". A dedicated profile collection or a separate JSON file would be cleaner for static user preferences.