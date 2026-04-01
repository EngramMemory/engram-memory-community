# Engram Community Edition

**Persistent semantic memory for AI agents. Self-hosted. Open source.**

[![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

---

Engram gives your AI agent persistent memory across sessions. Store, search, recall, and forget memories using semantic embeddings — all running on your own hardware with Qdrant and FastEmbed.

One repo, two interfaces: an **OpenClaw skill** and a **universal MCP server** that works with Claude Code, Cursor, Windsurf, and VS Code.

---

## What You Get

| Tool | What it does |
|---|---|
| `memory_store` | Save a memory with semantic embedding and auto-classification |
| `memory_search` | Semantic similarity search across all stored memories |
| `memory_recall` | Auto-inject relevant memories into agent context |
| `memory_forget` | Remove memories by ID or search match |

**Categories:** preference, fact, decision, entity, other — auto-detected from content.

---

## Quick Start

### 1. Deploy the backend

```bash
# Requires Docker
bash scripts/setup.sh
```

This starts Qdrant (vector DB) and FastEmbed (local embedding model) on your machine.

### 2. Connect your agent

**OpenClaw:**
```bash
clawhub install engrammemory
```

**Claude Code:**
```bash
claude mcp add engrammemory -- python mcp/server.py
```

**Cursor / Windsurf / VS Code** — add to `.mcp.json`:
```json
{
  "mcpServers": {
    "engrammemory": {
      "command": "python",
      "args": ["mcp/server.py"]
    }
  }
}
```

### 3. Use it

```python
# Store a memory
memory_store("User prefers TypeScript over JavaScript", category="preference")

# Search memories
memory_search("language preferences")

# Forget a memory
memory_forget(query="old project requirements")
```

---

## Architecture

```
┌─────────────────┐    ┌──────────────────────────────────────────┐
│   Your Agent    │    │        Three-Tier Recall Engine          │
│   (OpenClaw,    │───▶│  Tier 1: Hot Cache   (sub-ms, decay)    │
│    Claude Code, │    │  Tier 2: Hash Index  (O(1) LSH lookup)  │
│    Cursor, etc) │    │  Tier 3: Qdrant ANN  (full vector)      │
└─────────────────┘    └───────────┬──────────────────────────────┘
                                   │
                       ┌───────────▼───────────┐
                       │   FastEmbed (local)    │──▶  Qdrant (local)
                       └───────────────────────-┘
              All on your hardware. Nothing leaves your network.
```

### Repo Structure

```
engram-memory-community/
├── plugin.py               ← Main entry — routes all tool calls through recall engine
├── src/
│   └── recall/             ← Three-tier recall engine
│       ├── recall_engine.py    Hot → Hash → Vector pipeline
│       ├── hot_tier.py         Frequency-adjusted decay cache (sub-ms)
│       ├── multi_head_hasher.py  LSH O(1) candidate retrieval
│       ├── matryoshka.py       Vector slicing (768→64 dim)
│       └── models.py          MemoryResult, EngramConfig
├── skills/
│   └── openclaw/           ← OpenClaw skill (SKILL.md + plugin)
├── mcp/
│   └── server.py           ← MCP server (Claude Code, Cursor, Windsurf, VS Code)
├── scripts/                ← Setup + fallback scripts
│   ├── memory_store.py
│   ├── memory_search.py
│   ├── fastembed_service.py
│   └── setup.sh
├── docker/
│   └── fastembed/          ← FastEmbed container (Dockerfile + service)
├── config/
│   └── docker-compose.yml
├── docs/                   ← Architecture, examples, integration guides
├── README.md
└── LICENSE
```

The OpenClaw skill and the MCP server both route through `plugin.py`, which uses the three-tier recall engine for every store and search operation.

---

## OpenClaw Integration

Engram hooks into OpenClaw's agent lifecycle automatically:

- **`before_agent_start`** — searches for memories relevant to the user's message and injects them as context
- **`after_agent_response`** — extracts important facts from the conversation and stores them

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

---

## Configuration

| Option | Default | Description |
|---|---|---|
| `qdrantUrl` | `http://localhost:6333` | Qdrant vector database URL |
| `embeddingUrl` | `http://localhost:11435` | FastEmbed API endpoint |
| `embeddingModel` | `nomic-ai/nomic-embed-text-v1.5` | Embedding model |
| `collection` | `agent-memory` | Memory collection name |
| `autoRecall` | `true` | Auto-inject relevant memories |
| `autoCapture` | `true` | Auto-save important context |
| `maxRecallResults` | `5` | Max memories per auto-recall |
| `minRecallScore` | `0.35` | Minimum similarity threshold |
| `debug` | `false` | Enable debug logging |

---

## Requirements

- Python 3.10+
- Docker (for Qdrant + FastEmbed)
- 4GB+ RAM
- 10GB+ storage

---

## Data & Privacy

Engram is local-only. No data leaves your machine.

- **Memory tools** store and search vectors in your local Qdrant instance
- **Embeddings** are generated by FastEmbed running in a local Docker container
- **Context system** only reads `.md` files inside your project's `.context/` directory — never arbitrary project files
- **Auto-recall/auto-capture** (when enabled) operate within the OpenClaw agent lifecycle — memories stay in your local Qdrant
- **No telemetry, no phone-home, no external API calls**

The Docker image `engrammemory/fastembed` is built from `docker/fastembed/Dockerfile` in this repo. You can verify or rebuild it yourself.

---

## Engram Cloud

Need deduplication, compression, lifecycle management, multi-agent isolation, or analytics? [Engram Cloud](https://engrammemory.ai) adds enterprise intelligence on top of your self-hosted storage.

Your Qdrant stays yours. Engram Cloud processes in transit and stores nothing.

**SDKs:**
- Python: `pip install engrammemory-ai` — [PyPI](https://pypi.org/project/engrammemory-ai/)
- Node: `npm install engrammemory-ai` — [npm](https://www.npmjs.com/package/engrammemory-ai)
- [Dashboard](https://app.engrammemory.ai) | [API Docs](https://api.engrammemory.ai/docs)

---

## Contributing

Found a bug? Want to add a feature? PRs welcome.

---

## License

MIT — Use freely in personal and commercial projects.
