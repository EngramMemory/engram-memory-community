# Engram Cloud

When you need more than what runs locally — auto-scheduling, LLM-powered entity extraction, multi-agent isolation, or analytics — Engram Cloud adds enterprise intelligence on top of your self-hosted storage.

**Your Qdrant stays yours.** Engram Cloud processes vectors in transit and stores nothing unless you explicitly opt into overflow storage.

## What Cloud Adds

| Feature | Community | Cloud |
|---|---|---|
| Store / search / recall / forget | Yes | Yes |
| Auto-recall + auto-capture | Yes | Yes |
| Category detection | Yes | Yes |
| Three-tier recall (hot/hash/vector) | Yes | Yes |
| Knowledge graph (Kuzu) | Yes | Yes |
| Feedback loop (PREFERRED_OVER) | Yes | Yes |
| Deduplication | Manual, configurable threshold | Auto-scheduled + LLM merge summaries |
| Cross-linking (memory_connect) | Configurable max connections | Unlimited + bidirectional weighted traversal |
| Entity extraction | Regex-based (~70% coverage) | LLM-powered NER (full coverage) |
| Graph traversal | Configurable hops (default 1) | Multi-hop spreading activation |
| Concept clustering | Manual trigger (HDBSCAN) | Auto-scheduled every 6h + LLM synthesis |
| TurboQuant compression (6x) | No | Yes |
| Multi-agent isolation | No | Yes |
| Analytics dashboard | No | Yes |
| Batch operations | No | Yes |
| Overflow storage | No | Yes (opt-in) |

## Migration

Add two lines to your existing config:

```json
{
  "engramCloud": true,
  "engramApiKey": "eng_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

Your existing local memories continue to work. Cloud features apply to new operations immediately.

## Pricing

| Tier | Price | Tokens/mo | Queries/mo | Compression |
|---|---|---|---|---|
| **Free** | $0 | 500K | 5K | 100K vectors |
| **Builder** | $29/mo | 5M | 50K | 2M vectors |
| **Scale** | $199/mo | 50M | 500K | 20M vectors |
| **Enterprise** | Custom | Unlimited | Unlimited | Unlimited |

Learn more at [engrammemory.ai](https://engrammemory.ai).
