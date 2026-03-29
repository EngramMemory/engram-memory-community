#!/usr/bin/env python3
"""
FastEmbed HTTP service for Engram Memory
Provides lightweight embedding generation for memory storage
"""

import os
import sys
from pathlib import Path
import logging
from typing import List, Dict, Any
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastembed import TextEmbedding
import numpy as np

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FastEmbedService:
    def __init__(self, model_name: str = None):
        """Initialize FastEmbed service with specified model"""
        self.model_name = model_name or os.getenv("MODEL_NAME", "nomic-ai/nomic-embed-text-v1.5")
        self.embedding_model = None
        self._initialize_model()
    
    def _initialize_model(self):
        """Initialize the embedding model"""
        try:
            logger.info(f"Loading FastEmbed model: {self.model_name}")
            self.embedding_model = TextEmbedding(
                model_name=self.model_name,
                max_length=512
            )
            logger.info("FastEmbed model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load FastEmbed model: {e}")
            raise
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for list of texts"""
        try:
            embeddings = list(self.embedding_model.embed(texts))
            return [embedding.tolist() for embedding in embeddings]
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise

# Initialize FastEmbed service
service = FastEmbedService()
app = FastAPI(title="FastEmbed Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for testing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "model": service.model_name}

@app.post("/embeddings")
async def generate_embeddings(request: Dict[str, Any]):
    """Generate embeddings for input texts"""
    try:
        texts = request.get("texts", [])
        if not texts:
            raise HTTPException(status_code=400, detail="No texts provided")
        
        if not isinstance(texts, list):
            texts = [texts]
        
        embeddings = service.generate_embeddings(texts)
        
        return {
            "embeddings": embeddings,
            "model": service.model_name,
            "dimension": len(embeddings[0]) if embeddings else 0,
            "count": len(embeddings)
        }
    
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "FastEmbed Engram Memory",
        "model": service.model_name,
        "endpoints": ["/health", "/embeddings"]
    }

if __name__ == "__main__":
    logger.info("Starting FastEmbed service on localhost:8000")
    uvicorn.run(app, host="localhost", port=8000, log_level="info")