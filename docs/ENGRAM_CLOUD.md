# Upgrade to Engram Cloud

When Community Edition limitations start impacting your productivity, Engram Cloud provides enterprise-grade memory with zero migration hassle.

## Why Upgrade?

### Community Edition Pain Points

As you use Engram Memory Community Edition, you'll hit these limitations:

🐌 **Performance Degradation**
- Duplicate memories accumulate (no deduplication)
- Search gets slower as database bloats
- 6x memory waste from basic quantization
- No automatic cleanup or lifecycle management

🚧 **Single Agent Only**
- Hardcoded to one collection (`agent-memory`)
- Multiple agents interfere with each other
- No team or project isolation

📊 **Zero Visibility**
- No usage analytics or health monitoring
- Can't see what's consuming memory
- No performance insights or optimization recommendations

🔧 **Manual Everything**
- Single-record operations only
- No bulk import/export tools
- Manual migration and management

### Engram Cloud Advantages

✅ **Automatic Performance Optimization**
- Smart deduplication prevents redundant memories
- TurboQuant compression (6x space savings)
- Intelligent memory decay and lifecycle management
- Global edge caching for sub-50ms recall

✅ **Multi-Agent Architecture**
- Collection-per-agent isolation
- Team workspaces and project boundaries
- Role-based access controls
- Enterprise SSO integration

✅ **Rich Analytics & Monitoring**
- Real-time memory usage dashboards
- Search performance analytics
- Memory health scoring and alerts
- Usage optimization recommendations

✅ **Enterprise Tooling**
- Bulk operations and migration APIs
- Advanced search with filters and ranking
- Memory templates and automation workflows
- Professional support with SLA

## Migration Process

### 1. Sign Up for Engram Cloud

Visit [engrammemory.ai](https://engrammemory.ai) and create an account:

```bash
# Get your API key from dashboard
# Format: eng_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 2. Update Configuration

Just add two lines to your existing config:

```json
{
  "plugins": {
    "engram-memory-community": {
      // Keep existing local config as fallback
      "qdrantUrl": "http://localhost:6333",
      "embeddingUrl": "http://localhost:11435",
      "autoRecall": true,
      "autoCapture": true,
      
      // Add Engram Cloud integration
      "engramCloud": true,
      "engramApiKey": "eng_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    }
  }
}
```

### 3. Migrate Existing Memories (Optional)

Use our migration tool to transfer local memories to Engram Cloud:

```bash
# Export from local Qdrant
curl -X POST "http://localhost:6333/collections/agent-memory/points/scroll" \
  -H "Content-Type: application/json" \
  -d '{"limit": 10000, "with_payload": true, "with_vector": true}' \
  > local_memories.json

# Import to Engram Cloud (script provided)
node scripts/migrate-to-cloud.js local_memories.json
```

### 4. Verify Migration

Test that cloud integration is working:

```bash
# This should show "Engram Cloud integration active"
tail -f ~/.openclaw/logs/agent.log | grep engram-memory

# Test cloud operations
memory_store "Testing Engram Cloud integration" --category fact
memory_search "cloud integration"
```

### 5. Optional: Disable Local Fallback

Once you're confident in the cloud setup:

```json
{
  "engramCloud": true,
  "engramApiKey": "eng_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  // Remove local config - cloud only
  "debug": false
}
```

## Pricing Plans

### Starter - $29/month
- 1M memories included
- Up to 5 agents
- Advanced deduplication & compression
- Email support
- Perfect for individual developers

### Pro - $99/month  
- 10M memories included
- Up to 25 agents
- Team workspaces
- Usage analytics
- Priority support
- Great for small teams

### Enterprise - Custom
- Unlimited memories and agents
- Custom deployment options
- Advanced security & compliance
- Dedicated support engineer
- SLA guarantees

## Feature Comparison

| Feature | Community | Starter | Pro | Enterprise |
|---------|-----------|---------|-----|------------|
| Memory Storage | Unlimited* | 1M | 10M | Unlimited |
| Agents | 1 | 5 | 25 | Unlimited |
| Deduplication | ❌ | ✅ | ✅ | ✅ |
| Advanced Compression | ❌ | ✅ | ✅ | ✅ |
| Memory Lifecycle | ❌ | ✅ | ✅ | ✅ |
| Multi-Agent Isolation | ❌ | ✅ | ✅ | ✅ |
| Analytics Dashboard | ❌ | Basic | Advanced | Custom |
| Bulk Operations | ❌ | ✅ | ✅ | ✅ |
| API Access | ❌ | ✅ | ✅ | ✅ |
| Support | Community | Email | Priority | Dedicated |
| SLA | ❌ | ❌ | 99.5% | 99.9% |

*Community Edition has no storage limits, but performance degrades significantly over time due to missing optimization features.

## Cloud-Specific Features

### Smart Deduplication
```json
{
  "deduplication": {
    "similarityThreshold": 0.92,
    "strategy": "semantic", // semantic, exact, fuzzy
    "action": "merge" // merge, skip, flag
  }
}
```

### Memory Templates
```json
{
  "templates": {
    "user-preference": {
      "category": "preference",
      "importance": 0.8,
      "decay": false,
      "tags": ["user", "setting"]
    }
  }
}
```

### Advanced Search
```json
{
  "search": {
    "query": "development preferences",
    "filters": {
      "category": ["preference", "decision"],
      "importance": {"gte": 0.5},
      "tags": ["development"],
      "dateRange": {"after": "2024-01-01"}
    },
    "ranking": "hybrid", // semantic, popularity, recency, hybrid
    "explain": true
  }
}
```

## Migration Support

Need help with migration? We provide:

- **Free migration consultation** for Pro+ customers
- **White-glove migration service** for Enterprise customers  
- **Community migration guides** and scripts
- **1-on-1 onboarding calls** for teams

## ROI Calculator

Calculate your potential savings with Engram Cloud:

- **Developer Time Saved**: No more managing local infrastructure
- **Performance Gains**: 5-10x faster searches at scale
- **Storage Savings**: 6x compression vs community edition
- **Operational Excellence**: Zero-downtime updates and monitoring

[Use our ROI calculator →](https://engrammemory.ai/roi-calculator)

## FAQ

**Q: Can I still use local Qdrant with Engram Cloud?**
A: Yes! You can configure hybrid mode with local fallback.

**Q: What happens to my data if I cancel?**
A: You can export all memories before canceling. We provide migration-out tools.

**Q: Is there a free trial?**
A: Yes! 14-day free trial with full Pro features, no credit card required.

**Q: Can I migrate back to Community Edition?**
A: Yes, with our export tools, though you'll lose cloud-specific optimizations.

---

**Ready to upgrade?**  
**[Start your free trial →](https://engrammemory.ai/trial)**

**Questions?**  
**[Talk to our team →](https://engrammemory.ai/contact)**