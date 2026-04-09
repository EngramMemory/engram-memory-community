#!/usr/bin/env python3
"""
FastEmbed HTTP service for Engram Memory
Provides lightweight ONNX-based embedding generation for memory storage.

Uses fastembed 0.7.x with ONNX Runtime — native support for both x86_64 and ARM64/Apple Silicon.
"""

import os
import logging
from typing import List, Dict, Any
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastembed import TextEmbedding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("MODEL_NAME", "nomic-ai/nomic-embed-text-v1.5")

logger.info(f"Loading FastEmbed model: {MODEL_NAME}")
model = TextEmbedding(model_name=MODEL_NAME, max_length=512)
logger.info("FastEmbed model loaded successfully")

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
    return {"status": "healthy", "model": MODEL_NAME}


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
        "endpoints": ["/health", "/embeddings"],
    }


if __name__ == "__main__":
    logger.info("Starting FastEmbed service on localhost:8000")
    uvicorn.run(app, host="localhost", port=8000, log_level="info")
