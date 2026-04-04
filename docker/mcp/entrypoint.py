#!/usr/bin/env python3
"""
Engram Memory — Dockerized MCP Server
Runs the recall engine MCP server with SSE transport for container use.

Also exposes a /health endpoint and a REST API for direct testing
without an MCP client.

Usage:
    docker run -p 8585:8585 \
      -e QDRANT_URL=http://host.docker.internal:6333 \
      -e FASTEMBED_URL=http://host.docker.internal:11435 \
      engrammemory/mcp-server:latest
"""

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, "/app/recall")

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from recall_engine import EngramRecallEngine
from models import EngramConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("engram-mcp-docker")

# Config from env
QDRANT_URL = os.getenv("QDRANT_URL", "http://host.docker.internal:6333")
FASTEMBED_URL = os.getenv("FASTEMBED_URL", "http://host.docker.internal:11435")
COLLECTION = os.getenv("COLLECTION_NAME", "agent-memory")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")

app = FastAPI(title="Engram Memory MCP Server", version="2.0.0")
engine = None


@app.on_event("startup")
async def startup():
    global engine
    config = EngramConfig(
        qdrant_url=QDRANT_URL,
        embedding_url=FASTEMBED_URL,
        collection=COLLECTION,
        data_dir=DATA_DIR,
    )
    engine = EngramRecallEngine(config)
    await engine.warmup()
    logger.info(f"Recall engine ready — Qdrant: {QDRANT_URL}, Collection: {COLLECTION}")


@app.on_event("shutdown")
async def shutdown():
    if engine:
        await engine.shutdown()


@app.get("/health")
async def health():
    if not engine:
        return JSONResponse({"status": "starting"}, status_code=503)
    try:
        h = await engine.get_health()
        return h.to_dict()
    except Exception as e:
        return JSONResponse({"status": "error", "error": str(e)}, status_code=503)


@app.get("/tools")
async def list_tools():
    """List available MCP tools."""
    return {
        "tools": [
            {"name": "memory_store", "description": "Store a memory"},
            {"name": "memory_search", "description": "Search memories (three-tier recall)"},
            {"name": "memory_recall", "description": "Recall memories for context injection"},
            {"name": "memory_forget", "description": "Delete a memory"},
            {"name": "memory_consolidate", "description": "Merge near-duplicate memories"},
            {"name": "memory_connect", "description": "Discover cross-category connections"},
        ],
    }


@app.post("/store")
async def store(request: Request):
    body = await request.json()
    text = body.get("text", "")
    category = body.get("category", "other")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    try:
        doc_id = await engine.store(content=text, category=category, metadata=body.get("metadata"))
        return {"success": True, "memory_id": doc_id, "category": category}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/search")
async def search(request: Request):
    body = await request.json()
    query = body.get("query", "")
    limit = body.get("limit", 10)
    category = body.get("category")
    if not query:
        return JSONResponse({"error": "query is required"}, status_code=400)
    try:
        results = await engine.search(query=query, top_k=limit, category=category)
        return {
            "query": query,
            "total_results": len(results),
            "tiers_used": list(set(r.tier for r in results)),
            "results": [r.to_dict() for r in results],
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/forget")
async def forget(request: Request):
    body = await request.json()
    memory_id = body.get("memory_id")
    query = body.get("query")
    try:
        if memory_id:
            success = await engine.forget(memory_id)
            return {"success": success, "deleted": memory_id}
        if query:
            results = await engine.search(query=query, top_k=1)
            if not results:
                return {"success": False, "error": "No matching memory"}
            success = await engine.forget(results[0].doc_id)
            return {"success": success, "deleted": results[0].doc_id}
        return {"success": False, "error": "Provide memory_id or query"}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/consolidate")
async def consolidate(request: Request):
    body = await request.json()
    if not engine.consolidator:
        return JSONResponse({"error": "Consolidator not available"}, status_code=503)
    try:
        result = await engine.consolidator.consolidate(threshold=body.get("threshold", 0.95))
        return {"success": True, **result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/connect")
async def connect(request: Request):
    body = await request.json()
    doc_id = body.get("memory_id")
    query = body.get("query")
    if not engine.consolidator:
        return JSONResponse({"error": "Consolidator not available"}, status_code=503)
    try:
        if not doc_id and query:
            results = await engine.search(query=query, top_k=1)
            if results:
                doc_id = results[0].doc_id
        if not doc_id:
            return {"success": False, "error": "Provide memory_id or query"}
        result = await engine.consolidator.connect(doc_id=doc_id, max_connections=body.get("max_connections", 3))
        return {"success": True, **result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8585"))
    logger.info(f"Starting Engram MCP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
