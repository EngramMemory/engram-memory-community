#!/usr/bin/env python3
"""
Memory storage tool for Engram Memory
Stores content with embeddings in Qdrant
"""

import sys
import json
import uuid
import requests
from datetime import datetime
from typing import Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

class MemoryStore:
    def __init__(self, 
                 qdrant_host: str = "localhost",
                 qdrant_port: int = 6333,
                 fastembed_url: str = "http://localhost:11435",
                 collection_name: str = "agent-memory"):
        
        self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.fastembed_url = fastembed_url
        self.collection_name = collection_name
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Ensure the memory collection exists"""
        try:
            collections = self.qdrant_client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.collection_name not in collection_names:
                print(f"Creating collection: {self.collection_name}")
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=768, distance=Distance.COSINE)
                )
                print(f"Collection {self.collection_name} created successfully")
        except Exception as e:
            print(f"Failed to ensure collection: {e}")
            raise
    
    def _get_embeddings(self, text: str) -> list:
        """Get embeddings from FastEmbed service"""
        try:
            response = requests.post(
                f"{self.fastembed_url}/embeddings",
                json={"texts": [text]},
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return result["embeddings"][0]
        
        except Exception as e:
            print(f"Failed to get embeddings: {e}")
            raise
    
    def store_memory(self,
                    text: str,
                    category: str = "general",
                    importance: float = 0.5,
                    metadata: Optional[Dict] = None) -> str:
        """Store a memory with embeddings"""
        try:
            # Generate unique ID
            memory_id = str(uuid.uuid4())
            
            # Get embeddings
            embeddings = self._get_embeddings(text)
            
            # Prepare metadata
            payload = {
                "text": text,
                "category": category,
                "importance": importance,
                "timestamp": datetime.utcnow().isoformat(),
                "id": memory_id
            }
            
            if metadata:
                payload.update(metadata)
            
            # Store in Qdrant
            point = PointStruct(
                id=memory_id,
                vector=embeddings,
                payload=payload
            )
            
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            print(f"Memory stored successfully: {memory_id}")
            return memory_id
        
        except Exception as e:
            print(f"Failed to store memory: {e}")
            raise


def main():
    """CLI interface for memory storage"""
    if len(sys.argv) < 2:
        print("Usage: python memory_store.py <text> [category] [importance]")
        print("   or: python memory_store.py --json '<json_object>'")
        sys.exit(1)
    
    store = MemoryStore()
    
    if sys.argv[1] == "--json":
        # JSON input mode
        try:
            data = json.loads(sys.argv[2])
            memory_id = store.store_memory(
                data["text"],
                data.get("category", "general"),
                data.get("importance", 0.5),
                data.get("metadata")
            )
            print(json.dumps({"success": True, "memory_id": memory_id}))
        except Exception as e:
            print(json.dumps({"success": False, "error": str(e)}))
            sys.exit(1)
    else:
        # Simple CLI mode
        text = sys.argv[1]
        category = sys.argv[2] if len(sys.argv) > 2 else "general"
        importance = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
        
        try:
            memory_id = store.store_memory(text, category, importance)
            print(json.dumps({"success": True, "memory_id": memory_id}))
        except Exception as e:
            print(json.dumps({"success": False, "error": str(e)}))
            sys.exit(1)

if __name__ == "__main__":
    main()