#!/usr/bin/env python3
"""
FastEmbed HTTP service for Engram Memory
Provides lightweight ONNX-based embedding generation for memory storage.

Uses fastembed 0.7.x with ONNX Runtime — native support for both x86_64 and ARM64/Apple Silicon.
Includes optional cross-encoder reranking via TextCrossEncoder (fastembed 0.8+).
"""

import os
import logging
from typing import List, Dict, Any, Optional
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastembed import TextEmbedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("MODEL_NAME", "nomic-ai/nomic-embed-text-v1.5")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")

logger.info(f"Loading FastEmbed model: {MODEL_NAME}")
model = TextEmbedding(model_name=MODEL_NAME, max_length=512)
logger.info("FastEmbed model loaded successfully")

# Cross-encoder reranker — lazy-loaded on first /rerank request
_reranker: Optional[Any] = None
_reranker_loaded: bool = False


def _get_reranker():
    """Lazy-load the cross-encoder model on first use."""
    global _reranker, _reranker_loaded
    if _reranker_loaded:
        return _reranker
    try:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        logger.info(f"Loading cross-encoder reranker: {RERANKER_MODEL}")
        _reranker = TextCrossEncoder(model_name=RERANKER_MODEL)
        logger.info("Cross-encoder reranker loaded successfully")
    except Exception as e:
        logger.warning(f"Cross-encoder reranker unavailable: {e}")
        _reranker = None
    _reranker_loaded = True
    return _reranker


app = FastAPI(title="FastEmbed Service", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "model": MODEL_NAME, "backend": "fastembed-onnx"}


@app.post("/embeddings")
async def generate_embeddings(request: Dict[str, Any]):
    try:
        texts = request.get("texts", [])
        if not texts:
            raise HTTPException(status_code=400, detail="No texts provided")
        if not isinstance(texts, list):
            texts = [texts]

        # Task prefix for nomic-embed-text-v1.5
        embed_type = request.get("type", None)
        prefix_map = {"document": "search_document: ", "query": "search_query: "}
        prefix = prefix_map.get(embed_type)

        if prefix:
            texts = [f"{prefix}{t}" for t in texts]

        embeddings = [e.tolist() for e in model.embed(texts)]

        return {
            "embeddings": embeddings,
            "model": MODEL_NAME,
            "backend": "fastembed-onnx",
            "dimension": len(embeddings[0]) if embeddings else 0,
            "count": len(embeddings),
        }
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rerank")
async def rerank_documents(request: Dict[str, Any]):
    """Cross-encoder reranking using ms-marco-MiniLM-L-6-v2.

    Accepts: {"query": "...", "documents": ["doc1", "doc2", ...]}
    Returns: {"scores": [0.95, 0.23, ...]}

    Scores are raw cross-encoder logits (higher = more relevant).
    The reranker model is lazy-loaded on first call (~1s overhead).
    """
    query = request.get("query", "")
    documents = request.get("documents", [])

    if not query:
        raise HTTPException(status_code=400, detail="No query provided")
    if not documents:
        return {"scores": [], "model": RERANKER_MODEL}

    reranker = _get_reranker()
    if reranker is None:
        raise HTTPException(status_code=503, detail="Cross-encoder reranker not available")

    try:
        scores = list(reranker.rerank(query, documents))
        return {
            "scores": [float(s) for s in scores],
            "model": RERANKER_MODEL,
            "count": len(scores),
        }
    except Exception as e:
        logger.error(f"Reranking failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {
        "service": "FastEmbed Engram Memory",
        "version": "2.0.0",
        "model": MODEL_NAME,
        "reranker_model": RERANKER_MODEL,
        "backend": "fastembed-onnx",
        "endpoints": ["/health", "/embeddings", "/rerank"],
    }


if __name__ == "__main__":
    logger.info("Starting embedding service on localhost:8000")
    uvicorn.run(app, host="localhost", port=8000, log_level="info")
