#!/usr/bin/env python3
"""
Memory search tool for Engram Memory
Searches stored memories using semantic similarity
"""

import sys
import json
import requests
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

class MemorySearch:
    def __init__(self,
                 qdrant_host: str = "localhost", 
                 qdrant_port: int = 6333,
                 fastembed_url: str = "http://localhost:11435",
                 collection_name: str = "agent-memory"):
        
        self.qdrant_client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.fastembed_url = fastembed_url
        self.collection_name = collection_name
    
    def _get_query_embedding(self, query: str) -> List[float]:
        """Get embedding for search query"""
        try:
            response = requests.post(
                f"{self.fastembed_url}/embeddings",
                json={"texts": [query]},
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            return result["embeddings"][0]
        
        except Exception as e:
            print(f"Failed to get query embedding: {e}")
            raise
    
    def search(self,
              query: str,
              limit: int = 10,
              min_score: float = 0.0,
              category: Optional[str] = None,
              min_importance: Optional[float] = None,
              max_importance: Optional[float] = None) -> List[Dict[str, Any]]:
        """Search memories using semantic similarity"""
        try:
            # Get query embedding
            query_embedding = self._get_query_embedding(query)
            
            # Build filters
            filter_conditions = []
            
            if category:
                filter_conditions.append(
                    FieldCondition(key="category", match=MatchValue(value=category))
                )
            
            if min_importance is not None or max_importance is not None:
                range_filter = {}
                if min_importance is not None:
                    range_filter["gte"] = min_importance
                if max_importance is not None:
                    range_filter["lte"] = max_importance
                
                filter_conditions.append(
                    FieldCondition(key="importance", range=Range(**range_filter))
                )
            
            # Create filter
            search_filter = None
            if filter_conditions:
                search_filter = Filter(must=filter_conditions)
            
            # Perform search
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=search_filter,
                limit=limit,
                score_threshold=min_score
            )
            
            # Format results
            results = []
            for result in search_results:
                memory = {
                    "id": result.id,
                    "score": result.score,
                    "text": result.payload.get("text", ""),
                    "category": result.payload.get("category", "general"),
                    "importance": result.payload.get("importance", 0.5),
                    "timestamp": result.payload.get("timestamp", ""),
                    "metadata": {}
                }
                
                # Add any additional metadata
                for key, value in result.payload.items():
                    if key not in ["text", "category", "importance", "timestamp", "id"]:
                        memory["metadata"][key] = value
                
                results.append(memory)
            
            return results
        
        except Exception as e:
            print(f"Memory search failed: {e}")
            raise
    
    def get_by_category(self, category: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all memories from a specific category"""
        try:
            filter_condition = Filter(
                must=[FieldCondition(key="category", match=MatchValue(value=category))]
            )
            
            search_results = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter=filter_condition,
                limit=limit
            )
            
            results = []
            for result in search_results[0]:  # scroll returns (records, next_page_offset)
                memory = {
                    "id": result.id,
                    "text": result.payload.get("text", ""),
                    "category": result.payload.get("category", "general"),
                    "importance": result.payload.get("importance", 0.5),
                    "timestamp": result.payload.get("timestamp", ""),
                    "metadata": {}
                }
                
                # Add additional metadata
                for key, value in result.payload.items():
                    if key not in ["text", "category", "importance", "timestamp", "id"]:
                        memory["metadata"][key] = value
                
                results.append(memory)
            
            return results
        
        except Exception as e:
            print(f"Category search failed: {e}")
            raise
    


def main():
    """CLI interface for memory search"""
    if len(sys.argv) < 2:
        print("Usage: python memory_search.py <query> [limit] [min_score] [category]")
        print("   or: python memory_search.py --category <category_name>")
        sys.exit(1)
    
    searcher = MemorySearch()
    
    try:
        if sys.argv[1] == "--category":
            # Category search
            if len(sys.argv) < 3:
                print("Error: Category name required")
                sys.exit(1)
            
            category = sys.argv[2]
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
            
            results = searcher.get_by_category(category, limit)
            print(json.dumps({"results": results, "count": len(results)}, indent=2))
        
        else:
            # Semantic search
            query = sys.argv[1]
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
            min_score = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
            category = sys.argv[4] if len(sys.argv) > 4 else None
            
            results = searcher.search(
                query=query,
                limit=limit,
                min_score=min_score,
                category=category
            )
            
            print(json.dumps({
                "query": query,
                "results": results,
                "count": len(results)
            }, indent=2))
    
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(1)

if __name__ == "__main__":
    main()