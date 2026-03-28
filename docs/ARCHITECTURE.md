# Architecture Overview

How Engram Memory Community Edition works under the hood.

## High-Level Architecture

```
┌──────────────────────────────────────────────────────┐
│                   Your AI Agent                      │
│         (OpenClaw, Claude Code, Cursor, etc)         │
└───────────────┬──────────────────┬───────────────────┘
                │                  │
    ┌───────────▼──────┐  ┌───────▼──────────────┐
    │  OpenClaw Skill  │  │  MCP Server          │
    │  (skills/openclaw)│  │  (mcp/server.py)     │
    └───────────┬──────┘  └───────┬──────────────┘
                │                  │
                └────────┬─────────┘
                         │
              ┌──────────▼──────────┐
              │   Shared Scripts    │
              │   (scripts/)        │
              └─────┬─────────┬─────┘
                    │         │
          ┌─────────▼───┐ ┌──▼──────────────┐
          │  FastEmbed   │ │  Qdrant Vector  │
          │  (local)     │ │  Store (local)  │
          │  Port 11435  │ │  Port 6333      │
          └──────────────┘ └─────────────────┘
```

Two thin interfaces (OpenClaw skill + MCP server) share the same memory engine. Both talk to the same FastEmbed and Qdrant instances.

## Components

### 1. Plugin Core (`src/index.ts`)

**EngramMemoryPlugin Class:**
- Configuration management
- Embedding via FastEmbed
- Qdrant vector database operations
- Category detection (preference, decision, fact, entity, other)
- OpenClaw lifecycle hooks (auto-recall, auto-capture)

**Tools:**
- `memory_store` — Store new memories
- `memory_search` — Semantic search
- `memory_list` — Browse memories
- `memory_forget` — Delete memories
- `memory_profile` — User profile management

### 2. MCP Server (`mcp/server.py`)

Universal bridge for non-OpenClaw clients:
- `memory_store` — Store with embedding
- `memory_search` — Semantic similarity search
- `memory_recall` — Context-aware recall (higher threshold)
- `memory_forget` — Delete by ID or search match

Runs on stdio transport. Works with any MCP-compatible client.

### 3. Local Infrastructure

**Qdrant Vector Database:**
- Collection: `agent-memory`
- Vectors: 768-dimensional
- Distance: Cosine similarity
- Quantization: int8 scalar (4x memory reduction)

**FastEmbed API Server:**
- Model: `nomic-ai/nomic-embed-text-v1.5`
- Local HTTP API for embeddings
- CPU-optimized inference

## Data Flow

### Memory Storage

```
Agent → memory_store("I prefer TypeScript")
  → FastEmbed: embed text → [0.1, 0.3, -0.2, ...]
  → Qdrant: store vector + metadata (text, category, importance, timestamp)
  → Return: "Memory stored [preference]: I prefer TypeScript..."
```

### Memory Search

```
Agent → memory_search("language preferences")
  → FastEmbed: embed query → [0.1, 0.3, -0.2, ...]
  → Qdrant: cosine similarity search
  → Return: matching memories with scores
```

### Auto-Recall (OpenClaw)

```
User message → before_agent_start hook
  → Extract key terms
  → Search Qdrant for relevant memories
  → Inject matches as <recalled_memories> context
  → Agent generates response with memory context
```

## Data Structures

### Memory Object
```typescript
interface Memory {
  id: string;           // UUID
  text: string;         // Original content
  category: string;     // preference|fact|decision|entity|other
  importance: number;   // 0-1 score
  timestamp: string;    // ISO datetime
  tags: string[];       // Additional metadata
}
```

### Qdrant Point
```json
{
  "id": "uuid-here",
  "vector": [0.1, 0.3, -0.2, ...],
  "payload": {
    "text": "I prefer TypeScript",
    "category": "preference",
    "importance": 0.8,
    "timestamp": "2026-03-27T15:30:00Z",
    "tags": []
  }
}
```

### Configuration
```typescript
interface PluginConfig {
  qdrantUrl: string;
  embeddingUrl: string;
  embeddingModel: string;
  embeddingDimension: number;
  autoRecall: boolean;
  autoCapture: boolean;
  maxRecallResults: number;
  minRecallScore: number;
  debug: boolean;
}
```

## Security

- Local-only by default — all data stays on your infrastructure
- No external API calls — embeddings generated locally
- No telemetry or phone-home
