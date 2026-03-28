# Engram Cloud

When you need more than basic CRUD — deduplication, compression, lifecycle management, multi-agent isolation, or analytics — Engram Cloud adds enterprise intelligence on top of your self-hosted storage.

**Your Qdrant stays yours.** Engram Cloud processes vectors in transit and stores nothing unless you explicitly opt into overflow storage.

## What Cloud Adds

| Feature | Community | Cloud |
|---|---|---|
| Store / search / recall / forget | Yes | Yes |
| Auto-recall + auto-capture | Yes | Yes |
| Category detection | Yes | Yes |
| Deduplication | — | Yes |
| Memory lifecycle (decay + pruning) | — | Yes |
| TurboQuant compression (6x) | — | Yes |
| Multi-agent isolation | — | Yes |
| Analytics dashboard | — | Yes |
| Batch operations | — | Yes |
| Overflow storage | — | Yes (opt-in) |

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
