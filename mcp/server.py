#!/usr/bin/env python3
"""
Engram Memory — MCP Server

Universal MCP server exposing memory tools to any MCP-compatible client:
Claude Code, Cursor, Windsurf, VS Code, and other editors.

Talks to the same FastEmbed + Qdrant backend as the OpenClaw skill.

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
    FASTEMBED_URL       - FastEmbed service URL (default: http://localhost:8000)
    COLLECTION_NAME     - Qdrant collection name (default: agent-memory)
    DEBUG               - Enable debug logging (default: false)
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, Range
)

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
    """MCP Server exposing Engram memory tools: store, search, recall, forget."""

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        fastembed_url: str = "http://localhost:8000",
        collection_name: str = "agent-memory",
    ):
        self.qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.fastembed_url = fastembed_url
        self.collection_name = collection_name
        self.server = Server("engrammemory")
        self._register_tools()

        logger.info("Engram MCP Server initialized:")
        logger.info(f"  Qdrant: {qdrant_host}:{qdrant_port}")
        logger.info(f"  FastEmbed: {fastembed_url}")
        logger.info(f"  Collection: {collection_name}")

    # ── Infrastructure ──────────────────────────────────────────────

    def _ensure_collection(self):
        collections = [c.name for c in self.qdrant.get_collections().collections]
        if self.collection_name not in collections:
            logger.info(f"Creating collection: {self.collection_name}")
            self.qdrant.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            )

    def _embed(self, text: str) -> List[float]:
        resp = requests.post(
            f"{self.fastembed_url}/embeddings",
            json={"texts": [text]},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]

    # ── Tool Registration ───────────────────────────────────────────

    def _register_tools(self):
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="memory_store",
                    description="Store a memory with semantic embedding",
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
                    description="Search stored memories using semantic similarity",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Natural language search query"},
                            "limit": {"type": "integer", "default": 10, "description": "Max results"},
                            "min_score": {"type": "number", "default": 0.0, "description": "Minimum similarity (0-1)"},
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
                    description="Recall relevant memories for a given context (returns top matches above threshold)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "context": {"type": "string", "description": "Context to recall memories for"},
                            "limit": {"type": "integer", "default": 5, "description": "Max memories to recall"},
                            "min_score": {"type": "number", "default": 0.35, "description": "Minimum relevance threshold"},
                        },
                        "required": ["context"],
                    },
                ),
                Tool(
                    name="memory_forget",
                    description="Delete a memory by ID or by search match",
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

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # ── Tool Handlers ───────────────────────────────────────────────

    async def _handle_store(
        self, text: str, category: str = "other", importance: float = 0.5, **_
    ) -> Dict[str, Any]:
        try:
            self._ensure_collection()
            vector = self._embed(text)
            memory_id = str(uuid.uuid4())

            payload = {
                "text": text,
                "category": category,
                "importance": importance,
                "timestamp": datetime.now().isoformat(),
            }

            self.qdrant.upsert(
                collection_name=self.collection_name,
                points=[PointStruct(id=memory_id, vector=vector, payload=payload)],
            )

            logger.info(f"Stored memory {memory_id}: {text[:80]}...")
            return {"success": True, "memory_id": memory_id, **payload}
        except Exception as e:
            logger.error(f"Store failed: {e}")
            return {"success": False, "error": str(e)}

    async def _handle_search(
        self, query: str, limit: int = 10, min_score: float = 0.0, category: Optional[str] = None, **_
    ) -> Dict[str, Any]:
        try:
            self._ensure_collection()
            vector = self._embed(query)

            search_filter = None
            if category:
                search_filter = Filter(
                    must=[FieldCondition(key="category", match=MatchValue(value=category))]
                )

            results = self.qdrant.search(
                collection_name=self.collection_name,
                query_vector=vector,
                query_filter=search_filter,
                limit=limit,
                score_threshold=min_score,
            )

            memories = [
                {
                    "id": str(r.id),
                    "score": r.score,
                    "text": r.payload.get("text", ""),
                    "category": r.payload.get("category", "other"),
                    "importance": r.payload.get("importance", 0.5),
                    "timestamp": r.payload.get("timestamp", ""),
                }
                for r in results
            ]

            return {"query": query, "total_results": len(memories), "results": memories}
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {"query": query, "total_results": 0, "results": [], "error": str(e)}

    async def _handle_recall(
        self, context: str, limit: int = 5, min_score: float = 0.35, **_
    ) -> Dict[str, Any]:
        """Recall is search with a higher default threshold, designed for context injection."""
        return await self._handle_search(query=context, limit=limit, min_score=min_score)

    async def _handle_forget(
        self, memory_id: Optional[str] = None, query: Optional[str] = None, **_
    ) -> Dict[str, Any]:
        try:
            self._ensure_collection()

            if memory_id:
                self.qdrant.delete(
                    collection_name=self.collection_name,
                    points_selector=[memory_id],
                )
                return {"success": True, "deleted": memory_id}

            if query:
                results = await self._handle_search(query=query, limit=1, min_score=0.0)
                if not results["results"]:
                    return {"success": False, "error": "No matching memory found"}
                target_id = results["results"][0]["id"]
                self.qdrant.delete(
                    collection_name=self.collection_name,
                    points_selector=[target_id],
                )
                return {
                    "success": True,
                    "deleted": target_id,
                    "text": results["results"][0]["text"][:80],
                }

            return {"success": False, "error": "Provide either memory_id or query"}
        except Exception as e:
            logger.error(f"Forget failed: {e}")
            return {"success": False, "error": str(e)}


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Engram Memory MCP Server")
    parser.add_argument("--qdrant-host", default=os.getenv("QDRANT_HOST", "localhost"))
    parser.add_argument("--qdrant-port", type=int, default=int(os.getenv("QDRANT_PORT", "6333")))
    parser.add_argument("--fastembed-url", default=os.getenv("FASTEMBED_URL", "http://localhost:8000"))
    parser.add_argument("--collection", default=os.getenv("COLLECTION_NAME", "agent-memory"))

    args = parser.parse_args()

    mcp_server = EngramMCPServer(
        qdrant_host=args.qdrant_host,
        qdrant_port=args.qdrant_port,
        fastembed_url=args.fastembed_url,
        collection_name=args.collection,
    )

    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="engrammemory",
                server_version="1.0.0",
                capabilities=mcp_server.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
