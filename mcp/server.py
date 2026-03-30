#!/usr/bin/env python3
"""
Engram Memory — MCP Server (Three-Tier Recall Engine)

Universal MCP server exposing memory tools to any MCP-compatible client:
Claude Code, Cursor, Windsurf, VS Code, and other editors.

Now powered by the three-tier recall engine:
  Tier 1: Hot-Tier Cache (sub-ms, in-memory)
  Tier 2: Multi-Head Hash Index (O(1) candidate lookup)
  Tier 3: Qdrant Vector Search (full ANN fallback)

Usage:
    # Claude Code
    claude mcp add engrammemory -- python mcp/server.py

    # Cursor / Windsurf / VS Code — add to .mcp.json:
    {
      "mcpServers": {
        "engrammemory": {
          "command": "python",
          "args": ["mcp/server.py"]
        }
      }
    }

Environment Variables:
    QDRANT_HOST         - Qdrant host (default: localhost)
    QDRANT_PORT         - Qdrant port (default: 6333)
    FASTEMBED_URL       - FastEmbed service URL (default: http://localhost:11435)
    COLLECTION_NAME     - Qdrant collection name (default: agent-memory)
    DEBUG               - Enable debug logging (default: false)
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, Optional

# Add src/recall to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "recall"))

try:
    from recall_engine import EngramRecallEngine
    from models import EngramConfig
    RECALL_ENGINE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Recall engine not available ({e}). Falling back to direct Qdrant.", file=sys.stderr)
    RECALL_ENGINE_AVAILABLE = False

try:
    from mcp.server import NotificationOptions, Server
    from mcp.server.models import InitializationOptions
    from mcp.types import (
        CallToolRequest, CallToolResult, TextContent, Tool,
        ListToolsRequest, ListToolsResult,
    )
except ImportError:
    print("Error: mcp package not found. Install with: pip install mcp", file=sys.stderr)
    sys.exit(1)

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", "").lower() in ["true", "1"] else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("engram-mcp")


class EngramMCPServer:
    """MCP Server with three-tier recall: hot cache → hash index → vector search."""

    def __init__(self, config: EngramConfig):
        self.config = config
        self.engine: Optional[EngramRecallEngine] = None
        self.server = Server("engrammemory")
        self._register_tools()

        logger.info("Engram MCP Server initialized:")
        logger.info(f"  Qdrant: {config.qdrant_url}")
        logger.info(f"  FastEmbed: {config.embedding_url}")
        logger.info(f"  Collection: {config.collection}")
        logger.info(f"  Recall Engine: {'enabled' if RECALL_ENGINE_AVAILABLE else 'disabled (fallback mode)'}")

    async def startup(self):
        """Initialize the recall engine."""
        if RECALL_ENGINE_AVAILABLE:
            self.engine = EngramRecallEngine(self.config)
            await self.engine.warmup()
            logger.info("Recall engine warmed up — three-tier search active")
        else:
            logger.warning("Running without recall engine — single-tier Qdrant only")

    async def shutdown(self):
        """Persist state and clean up."""
        if self.engine:
            await self.engine.shutdown()
            logger.info("Recall engine shut down — state persisted")

    # ── Tool Registration ───────────────────────────────────────────

    def _register_tools(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="memory_store",
                    description="Store a memory with semantic embedding (indexed into hot-tier cache and hash index)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Text content to store"},
                            "category": {
                                "type": "string",
                                "enum": ["preference", "fact", "decision", "entity", "other"],
                                "default": "other",
                                "description": "Memory category",
                            },
                            "importance": {
                                "type": "number",
                                "default": 0.5,
                                "minimum": 0.0,
                                "maximum": 1.0,
                                "description": "Importance score (0-1)",
                            },
                        },
                        "required": ["text"],
                    },
                ),
                Tool(
                    name="memory_search",
                    description="Search memories using three-tier recall: hot cache (sub-ms) → hash index (O(1)) → vector search (fallback)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Natural language search query"},
                            "limit": {"type": "integer", "default": 10, "description": "Max results"},
                            "category": {
                                "type": "string",
                                "enum": ["preference", "fact", "decision", "entity", "other"],
                                "description": "Filter by category",
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="memory_recall",
                    description="Recall relevant memories for context injection (higher threshold, designed for auto-recall)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "context": {"type": "string", "description": "Context to recall memories for"},
                            "limit": {"type": "integer", "default": 5, "description": "Max memories to recall"},
                        },
                        "required": ["context"],
                    },
                ),
                Tool(
                    name="memory_forget",
                    description="Delete a memory from all tiers (hot cache, hash index, and vector store)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "memory_id": {"type": "string", "description": "UUID of memory to delete"},
                            "query": {"type": "string", "description": "Search query to find and delete the best match"},
                        },
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            logger.info(f"Tool call: {name} — {arguments}")

            if name == "memory_store":
                result = await self._handle_store(**arguments)
            elif name == "memory_search":
                result = await self._handle_search(**arguments)
            elif name == "memory_recall":
                result = await self._handle_recall(**arguments)
            elif name == "memory_forget":
                result = await self._handle_forget(**arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")

            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    # ── Tool Handlers ───────────────────────────────────────────────

    async def _handle_store(
        self, text: str, category: str = "other", importance: float = 0.5, **_
    ) -> Dict[str, Any]:
        try:
            if self.engine:
                doc_id = await self.engine.store(
                    content=text,
                    category=category,
                    metadata={"importance": importance},
                )
                logger.info(f"Stored memory {doc_id} via recall engine")
                return {"success": True, "memory_id": doc_id, "category": category}
            else:
                return {"success": False, "error": "Recall engine not available"}
        except Exception as e:
            logger.error(f"Store failed: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_search(
        self, query: str, limit: int = 10, category: Optional[str] = None, **_
    ) -> Dict[str, Any]:
        try:
            if self.engine:
                results = await self.engine.search(
                    query=query,
                    top_k=limit,
                    category=category,
                )
                memories = [r.to_dict() for r in results]
                tiers_used = set(r.tier for r in results)

                return {
                    "query": query,
                    "total_results": len(memories),
                    "tiers_used": list(tiers_used),
                    "results": memories,
                }
            else:
                return {"query": query, "total_results": 0, "results": [], "error": "Recall engine not available"}
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {"query": query, "total_results": 0, "results": [], "error": str(e)}

    async def _handle_recall(
        self, context: str, limit: int = 5, **_
    ) -> Dict[str, Any]:
        """Recall = search with higher threshold, for context injection."""
        return await self._handle_search(query=context, limit=limit)

    async def _handle_forget(
        self, memory_id: Optional[str] = None, query: Optional[str] = None, **_
    ) -> Dict[str, Any]:
        try:
            if not self.engine:
                return {"success": False, "error": "Recall engine not available"}

            if memory_id:
                success = await self.engine.forget(memory_id)
                return {"success": success, "deleted": memory_id}

            if query:
                results = await self.engine.search(query=query, top_k=1)
                if not results:
                    return {"success": False, "error": "No matching memory found"}
                target = results[0]
                success = await self.engine.forget(target.doc_id)
                return {"success": success, "deleted": target.doc_id, "text": target.content[:80]}

            return {"success": False, "error": "Provide either memory_id or query"}
        except Exception as e:
            logger.error(f"Forget failed: {e}")
            return {"success": False, "error": str(e)}


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Engram Memory MCP Server")
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--fastembed-url", default=os.getenv("FASTEMBED_URL", "http://localhost:11435"))
    parser.add_argument("--collection", default=os.getenv("COLLECTION_NAME", "agent-memory"))

    args = parser.parse_args()

    config = EngramConfig(
        qdrant_url=args.qdrant_url,
        embedding_url=args.fastembed_url,
        collection=args.collection,
        debug=os.getenv("DEBUG", "").lower() in ["true", "1"],
    )

    mcp_server = EngramMCPServer(config)
    await mcp_server.startup()

    from mcp.server.stdio import stdio_server

    try:
        async with stdio_server() as (read_stream, write_stream):
            await mcp_server.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="engrammemory",
                    server_version="2.0.0",
                    capabilities=mcp_server.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    finally:
        await mcp_server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
