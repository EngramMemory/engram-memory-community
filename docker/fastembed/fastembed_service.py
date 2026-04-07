#!/usr/bin/env python3
"""
FastEmbed HTTP service for Engram Memory
Provides lightweight embedding generation for memory storage.

Supports two backends (controlled by EMBED_BACKEND env var):
  - "fastembed"              — ONNX-based, best on x86_64
  - "sentence-transformers"  — PyTorch-based, native ARM64/Apple Silicon support
"""

import os
import logging
from typing import List, Dict, Any
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EMBED_BACKEND = os.getenv("EMBED_BACKEND", "fastembed")


class FastEmbedBackend:
    """ONNX-based backend using fastembed (best for x86_64)."""

    def __init__(self, model_name: str):
        from fastembed import TextEmbedding
        self.model_name = model_name
        logger.info(f"Loading FastEmbed model: {model_name}")
        self.model = TextEmbedding(model_name=model_name, max_length=512)
        logger.info("FastEmbed model loaded successfully")

    def embed(self, texts: List[str], prefix: str = None) -> List[List[float]]:
        if prefix:
            texts = [f"{prefix}{t}" for t in texts]
        embeddings = list(self.model.embed(texts))
        return [e.tolist() for e in embeddings]


class SentenceTransformerBackend:
    """PyTorch-based backend using sentence-transformers (native ARM64 support)."""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        self.model_name = model_name
        logger.info(f"Loading SentenceTransformer model: {model_name}")
        self.model = SentenceTransformer(model_name, trust_remote_code=True)
        logger.info("SentenceTransformer model loaded successfully")

    def embed(self, texts: List[str], prefix: str = None) -> List[List[float]]:
        if prefix:
            texts = [f"{prefix}{t}" for t in texts]
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        return [e.tolist() for e in embeddings]


def _create_backend(model_name: str):
    """Factory: pick backend based on EMBED_BACKEND env var."""
    if EMBED_BACKEND == "sentence-transformers":
        return SentenceTransformerBackend(model_name)
    return FastEmbedBackend(model_name)


# Initialize
MODEL_NAME = os.getenv("MODEL_NAME", "nomic-ai/nomic-embed-text-v1.5")
backend = _create_backend(MODEL_NAME)

app = FastAPI(title="FastEmbed Service", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "model": MODEL_NAME, "backend": EMBED_BACKEND}


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

        embeddings = backend.embed(texts, prefix=prefix)

        return {
            "embeddings": embeddings,
            "model": MODEL_NAME,
            "backend": EMBED_BACKEND,
            "dimension": len(embeddings[0]) if embeddings else 0,
            "count": len(embeddings),
        }
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {
        "service": "FastEmbed Engram Memory",
        "model": MODEL_NAME,
        "backend": EMBED_BACKEND,
        "endpoints": ["/health", "/embeddings"],
    }


if __name__ == "__main__":
    logger.info(f"Starting embedding service (backend={EMBED_BACKEND}) on localhost:8000")
    uvicorn.run(app, host="localhost", port=8000, log_level="info")
