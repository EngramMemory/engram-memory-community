# Engram Context System

Structured codebase documentation with natural language search. Initialize any project with a `.context/` directory, then query it with plain English.

## Quick Start

```bash
# Initialize context for your project
engram-context init /path/to/project --template web-app

# Build search index
engram-context index

# Search context files
engram-context find "authentication patterns"

# Ask questions in natural language
engram-ask "How does authentication work?"

# Semantic search (requires FastEmbed)
engram-semantic find "user login process"
```

## What You Get

Each project gets a `.context/` directory with structured documentation:

```
.context/
├── metadata.yaml       # Project configuration
├── architecture.md     # System architecture
├── patterns.md         # Code patterns and standards
├── apis.md             # API documentation
├── development.md      # Development workflows
├── troubleshooting.md  # Common issues and solutions
└── index.db            # Search index (auto-generated)
```

## Templates

| Template | Best for |
|---|---|
| `web-app` | Full-stack web apps (React/Vue + Node/Python + DB) |
| `python-api` | Python API servers (FastAPI, Django) |
| `generic` | Any project type |

## CLI Tools

### `engram-context` — Core Management
```bash
engram-context init <path> --template <type>   # Initialize project context
engram-context index                            # Build/rebuild search index
engram-context find "query"                     # Keyword search
engram-context status                           # Show system status
engram-context validate                         # Check context structure
```

### `engram-ask` — Natural Language Queries
```bash
engram-ask "How does authentication work?"      # Ask questions
engram-ask interactive                          # Interactive Q&A session
engram-ask examples                             # Show example questions
```

### `engram-semantic` — Embedding-Based Search
```bash
engram-semantic find "user login process"       # Semantic similarity search
engram-semantic index                           # Build semantic index
engram-semantic status                          # Check service status
engram-semantic test-service                    # Test FastEmbed connection
```

## How It Works

- **Keyword search** uses a SQLite index over your `.context/` markdown files
- **Natural language queries** classify your question, extract keywords, and search across context files with relevance scoring
- **Semantic search** embeds your query via FastEmbed and compares against embedded context files using cosine similarity

All searches are scoped to the current project's `.context/` directory.
