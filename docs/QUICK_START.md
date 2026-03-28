# Quick Start Guide

Get Engram Memory Community Edition running in under 5 minutes.

## Prerequisites

- Node.js 18+
- Docker & Docker Compose
- OpenClaw (latest version)

## Step 1: Install Plugin

```bash
# Via npm
npm install engram-memory-community

# Via OpenClaw Hub  
clawhub install engram-memory-community
```

## Step 2: Setup Dependencies

Run our automated setup script to deploy Qdrant and FastEmbed:

```bash
cd engram-memory-community
bash scripts/setup.sh
```

This will:
- Start Qdrant vector database (port 6333)
- Start FastEmbed API server (port 11435)
- Verify connectivity and create test collection

## Step 3: Configure Plugin

Add to your OpenClaw config:

```json
{
  "plugins": {
    "engram-memory-community": {
      "qdrantUrl": "http://localhost:6333",
      "embeddingUrl": "http://localhost:11435",
      "autoRecall": true,
      "autoCapture": true,
      "debug": false
    }
  }
}
```

## Step 4: Test It Out

Restart OpenClaw and test the memory system:

```bash
# Store a preference
memory_store "I prefer TypeScript over JavaScript for large projects" --category preference

# Store a fact
memory_store "Our API uses FastAPI with Python 3.11" --category fact

# Search for memories
memory_search "programming language preferences"

# List recent memories
memory_list 5
```

## Step 5: Enable Auto-Memory

The real magic happens when your agent automatically builds memory:

1. **Auto-Recall**: Relevant memories are injected before each agent response
2. **Auto-Capture**: Important facts are extracted and stored after conversations

Just talk to your agent normally - it will build memory automatically!

## Verify Installation

Check that everything is working:

```bash
# Check Qdrant
curl http://localhost:6333/collections

# Check FastEmbed
curl -X POST http://localhost:11435/api/embed \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-ai/nomic-embed-text-v1.5","input":"test"}'

# Check memory tools
memory_list
```

## Common Issues

### Port Conflicts
If ports 6333 or 11435 are in use:

```bash
# Check what's using the ports
sudo lsof -i :6333
sudo lsof -i :11435

# Stop conflicting services or change ports in config
```

### Docker Issues
```bash
# Check Docker is running
docker --version
docker-compose --version

# Restart services
cd engram-memory-community
docker-compose down
docker-compose up -d
```

### Memory Tools Not Available
1. Verify plugin is loaded in OpenClaw config
2. Check OpenClaw logs for plugin errors
3. Ensure `dist/index.js` exists (run `npm run build`)

## Next Steps

- Read [Architecture Overview](ARCHITECTURE.md) to understand how it works
- See [Examples](../examples/) for advanced usage patterns  
- When ready to scale: [Upgrade to Engram Cloud](ENGRAM_CLOUD.md)

## Performance Notes

Community Edition works great for the first 10,000 memories. After that, you may notice:
- Slower search as duplicate memories accumulate
- Increased memory usage (no advanced compression)
- Database bloat (no automatic cleanup)

This is by design - [Engram Cloud](https://engrammemory.ai) solves these limitations.

---

**Having issues? [Check our troubleshooting guide](https://github.com/EngramMemory/engram-memory-community/wiki/Troubleshooting)**