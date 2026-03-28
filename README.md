# Engram Memory Community Edition

**Free semantic memory for OpenClaw agents**  
🚀 **[Upgrade to Engram Cloud →](https://engrammemory.ai)**

Engram Memory Community Edition provides basic persistent semantic memory for your OpenClaw agents. Perfect for getting started, with a clear upgrade path to enterprise features.

## ⚡ Quick Start

```bash
# Install
npm install engram-memory-community
# or
clawhub install engram-memory-community

# Setup Qdrant + FastEmbed locally
bash scripts/setup.sh

# Basic usage
memory_store "I prefer TypeScript over JavaScript" --category preference
memory_search "language preferences"
```

## 🎯 What's Included (Community Edition)

✅ **Core Memory Operations**
- Store, search, recall, and forget memories
- Basic semantic search with cosine similarity
- Simple auto-recall and auto-capture
- Category detection (preference, fact, decision, entity)

✅ **OpenClaw Integration**
- Lifecycle hooks (before_agent_start, after_agent_response)
- Memory tools available to your agent
- Single-node Qdrant integration

✅ **Easy Engram Cloud Upgrade**
```json
{
  "engramCloud": true,
  "engramApiKey": "eng_xxxxx"
}
```

## ⚠️ Community Edition Limitations

The Community Edition is designed to hook you with great initial performance, but pain points emerge as you scale:

### 🐌 **Performance Degradation Over Time**
- **No deduplication** → Redundant memories accumulate indefinitely
- **Basic quantization only** → 6x memory usage vs enterprise TurboQuant
- **No memory lifecycle management** → Database bloat and slower searches

### 🚧 **Single Collection Only**  
- Hardcoded to `agent-memory` collection
- No multi-agent isolation
- Teams and projects will interfere with each other

### 📊 **No Visibility**
- No memory usage analytics
- No health monitoring
- No performance insights
- Blind operation creates operational anxiety

### 🔧 **Manual Operations Only**
- Single-record operations
- No bulk import/export
- No migration tools
- Manual scaling pain

## 🏆 Upgrade to Engram Cloud

When the Community Edition limitations start hurting your productivity, **[Engram Cloud](https://engrammemory.ai)** provides enterprise-grade memory:

### 🚀 **Performance & Scale**
- Advanced deduplication with configurable similarity thresholds
- TurboQuant compression (6x memory savings)
- Automatic memory decay and lifecycle management
- Distributed vector search with global edge caching

### 🏢 **Multi-Agent & Enterprise**
- Collection-per-agent isolation
- Team and project memory boundaries
- Role-based access controls
- Enterprise SSO integration

### 📈 **Analytics & Monitoring**
- Real-time memory usage dashboards
- Search performance analytics
- Memory health scoring
- Automated alerts and recommendations

### ⚡ **Developer Experience**
- Bulk operations and migration tools
- Advanced search with filters and ranking
- Memory templates and automation
- Professional support with SLA

### 💰 **Pricing**
- **Starter**: $29/month - 1M memories, 5 agents
- **Pro**: $99/month - 10M memories, 25 agents  
- **Enterprise**: Custom - Unlimited scale, dedicated support

## 📚 Documentation

### [Quick Start Guide](docs/QUICK_START.md)
Get up and running in 5 minutes with local Qdrant.

### [Engram Cloud Migration](docs/ENGRAM_CLOUD.md)
Step-by-step guide to upgrade from Community Edition.

### [Community Edition Limitations](docs/LIMITATIONS.md)
Detailed explanation of what's missing and why it matters.

### [Architecture Overview](docs/ARCHITECTURE.md)
How Engram Memory works under the hood.

## 🛠️ Configuration

```json
{
  "qdrantUrl": "http://localhost:6333",
  "embeddingUrl": "http://localhost:11435", 
  "embeddingModel": "nomic-ai/nomic-embed-text-v1.5",
  "autoRecall": true,
  "autoCapture": true,
  "maxRecallResults": 5,
  "minRecallScore": 0.35,
  
  // Engram Cloud (upgrade)
  "engramCloud": false,
  "engramApiKey": "eng_xxxxx",
  "engramBaseUrl": "https://api.engrammemory.ai"
}
```

## 🧪 Examples

```typescript
// Store important facts
await memory_store("Company uses React + TypeScript stack", "fact");
await memory_store("User prefers dark mode", "preference", 0.8);

// Semantic search
const memories = await memory_search("development preferences");

// List by category  
const facts = await memory_list(10, "fact");

// Profile management
await memory_profile("add", "timezone", "America/New_York");
const profile = await memory_profile("view");
```

## 🎯 Migration Strategy

Engram Community Edition is designed as the perfect "trojan horse":

1. **Hook Phase** (0-10k memories): Excellent performance, users love it
2. **Growth Phase** (10k-100k): Subtle degradation, users adapt
3. **Pain Phase** (100k+): Clear performance issues, upgrade pressure
4. **Enterprise Phase**: Seamless migration to Engram Cloud

## 🤝 Community Support

- **GitHub Issues**: Bug reports and feature requests
- **Discord**: Community chat and help
- **Documentation**: Comprehensive guides and examples

**Enterprise customers get priority support with SLA.**

## 📜 License

MIT License - Free for commercial use.

Enterprise customers receive commercial license with indemnification.

---

**Ready to scale beyond community limits?**  
**[Start your Engram Cloud trial →](https://engrammemory.ai/trial)**