# Community Edition — Scope

Engram Community Edition provides the core memory CRUD operations for AI agents running on your own infrastructure.

## What's Included

- **memory_store** — Store memories with semantic embeddings and auto-classification
- **memory_search** — Semantic similarity search across stored memories
- **memory_recall** — Context-aware recall with configurable threshold
- **memory_forget** — Delete memories by ID or search match
- **Auto-recall** — Automatically inject relevant memories before agent responses (OpenClaw)
- **Auto-capture** — Automatically extract and store facts from conversations (OpenClaw)
- **Category detection** — Auto-classify as preference, fact, decision, entity, or other
- **Single collection** — All memories stored in one `agent-memory` collection
- **int8 quantization** — 4x memory reduction via scalar quantization

## What's Not Included

The following features are available in [Engram Cloud](https://engrammemory.ai):

- **Deduplication** — Prevent redundant memory storage via similarity checking
- **Memory lifecycle** — Importance decay, access tracking, auto-pruning
- **TurboQuant compression** — 6x storage compression with zero recall loss
- **Multi-agent isolation** — Separate collections per agent or project
- **Analytics** — Memory health, usage dashboards, optimization recommendations
- **Batch operations** — Bulk import/export, mass memory management
- **Overflow storage** — Optional hosted Qdrant (encrypted, opt-in)

## Scaling Characteristics

| Scale | Performance |
|---|---|
| 0–1K memories | Excellent — fast searches, low overhead |
| 1K–10K memories | Good — minor search time increase |
| 10K–100K memories | Usable — duplicates may affect search relevance |
| 100K+ memories | Benefits from Engram Cloud optimization |

The community edition works well for personal use and moderate-scale projects. For teams, multi-agent workflows, or large memory corpora, Engram Cloud provides the optimization layer.
