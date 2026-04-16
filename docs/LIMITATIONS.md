# Community Edition — Features & Defaults

Engram Community Edition is a fully functional memory system for AI agents running on your own infrastructure. All core features are included; defaults are conservative but configurable.

## What's Included

- **memory_store** — Store memories with semantic embeddings and auto-classification
- **memory_search** — Three-tier recall: hot cache, hash index, vector search
- **memory_recall** — Context-aware recall with configurable threshold
- **memory_forget** — Delete memories by ID or search match
- **memory_consolidate** — Find and merge near-duplicate memories (configurable threshold)
- **memory_connect** — Discover cross-category connections via the entity graph
- **memory_feedback** — Report which results were useful to improve future ranking
- **Auto-recall** — Automatically inject relevant memories before agent responses
- **Auto-capture** — Automatically extract and store facts from conversations
- **Category detection** — Auto-classify as preference, fact, decision, entity, or other
- **Three-tier recall** — Hot-tier ACT-R cache, multi-head hash index, Qdrant ANN search
- **Knowledge graph** — Embedded Kuzu graph for entity tracking and spreading activation
- **Consolidation** — Manual dedup, cross-linking, and HDBSCAN concept clustering
- **Feedback loop** — PREFERRED_OVER edges in graph improve reranking over time
- **int8 quantization** — 4x memory reduction via scalar quantization

## Configurable Parameters

All defaults can be overridden via environment variables:

| Parameter | Env Var | Default | Description |
|-----------|---------|---------|-------------|
| Hash heads | `ENGRAM_HASH_HEADS` | 6 | Number of independent hash tables |
| Hash bits | `ENGRAM_HASH_BITS` | 14 | Bits per hash signature |
| Hot-tier max size | `ENGRAM_HOT_TIER_MAX` | 1000 | Max entries in hot-tier cache |
| ACT-R max timestamps | `ENGRAM_ACTR_MAX_TIMESTAMPS` | 50 | Timestamp cap per memory |
| Graph max hops | `ENGRAM_GRAPH_MAX_HOPS` | 1 | Max traversal depth |
| Graph max entities | `ENGRAM_GRAPH_MAX_ENTITIES` | 500 | Max entity nodes in graph |
| Dedup threshold | `ENGRAM_DEDUP_THRESHOLD` | 0.95 | Cosine similarity threshold for dedup |
| Max connections | `ENGRAM_MAX_CONNECTIONS` | 3 | Max connections per connect call |

## Scaling Characteristics

| Scale | Performance |
|---|---|
| 0-1K memories | Excellent — hot-tier handles most queries sub-ms |
| 1K-10K memories | Good — hash tier and vector search share the load |
| 10K-100K memories | Usable — consider running consolidation periodically |
| 100K+ memories | Benefits from tuning hash heads/bits and hot-tier size |

## What Engram Cloud Adds

For hives, multi-agent workflows, or large memory corpora, [Engram Cloud](https://engrammemory.ai) adds:

- **TurboQuant compression** — 6x storage compression with zero recall loss
- **Multi-agent isolation** — Separate collections per agent or project
- **Analytics dashboard** — Memory health, usage, optimization recommendations
- **Batch operations** — Bulk import/export, mass memory management
- **Overflow storage** — Optional hosted Qdrant (encrypted, opt-in)
- **Auto-scheduled consolidation** — Runs automatically on a cadence
- **LLM-powered NER** — Full entity extraction coverage beyond regex
- **Multi-hop traversal** — Deep graph exploration for complex queries
