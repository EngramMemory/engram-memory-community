"""
Engram Memory — Data Models
=============================
Shared data structures for the recall engine.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List


@dataclass
class MemoryResult:
    """
    A single memory returned from the recall engine.

    The `tier` field tells you how fast the retrieval was:
    - "hot"    → Sub-millisecond, from frequency cache
    - "hash"   → O(1) lookup, from multi-head hash index
    - "vector" → Standard ANN search from Qdrant
    """
    doc_id: str
    content: str
    score: float              # Final relevance score (0-1)
    tier: str                 # "hot" | "hash" | "vector"
    category: str             # preference, fact, decision, entity, other
    metadata: Dict = field(default_factory=dict)
    created_at: float = 0.0
    access_count: int = 0
    strength: float = 0.0     # Ebbinghaus strength (hot-tier only)
    similarity: float = 0.0   # Raw cosine similarity

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "content": self.content,
            "score": round(self.score, 4),
            "tier": self.tier,
            "category": self.category,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "access_count": self.access_count,
            "strength": round(self.strength, 4),
            "similarity": round(self.similarity, 4),
        }


@dataclass
class EngramConfig:
    """
    Configuration for the Engram Recall Engine.

    All defaults are tuned for Community Edition on a single machine.
    """
    # Qdrant connection
    qdrant_url: str = "http://localhost:6333"
    collection: str = "agent-memory"

    # FastEmbed connection
    embedding_url: str = "http://localhost:11435"
    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"
    embedding_dim: int = 768

    # Matryoshka slicing
    fast_dim: int = 64        # For Multi-Head Hashing
    medium_dim: int = 256     # For candidate pre-filtering
    full_dim: int = 768       # For final re-ranking

    # Multi-Head Hasher
    hasher_num_heads: int = 4       # Community: max 4
    hasher_hash_size: int = 12      # Community: max 12 bits
    hasher_seed: int = 42           # Deterministic projections
    hasher_persist_path: str = ".engram/hash_index.pkl"

    # Hot-Tier Cache
    hot_tier_max_size: int = 1000   # Community: max 1000
    hot_tier_decay_rate: float = 0.1
    hot_tier_similarity_threshold: float = 0.70
    hot_tier_persist_path: str = ".engram/hot_tier.json"
    hot_tier_sweep_interval: float = 3600.0  # Decay sweep every hour

    # Recall behavior
    auto_recall: bool = True
    auto_capture: bool = True
    max_recall_results: int = 5
    min_recall_score: float = 0.35

    # Search behavior
    search_top_k: int = 10
    hash_fallback_to_vector: bool = True  # If hash returns 0, do full scan
    hot_tier_context_inject: bool = True   # Inject hot memories into prompt

    # Persistence
    data_dir: str = ".engram"
    auto_persist: bool = True
    persist_interval: float = 300.0  # Auto-save every 5 minutes

    # Debug
    debug: bool = False

    def ensure_data_dir(self):
        """Create data directory if it doesn't exist."""
        import os
        os.makedirs(self.data_dir, exist_ok=True)


@dataclass
class RecallEngineHealth:
    """Health check response from the recall engine."""
    status: str                       # "healthy" | "degraded" | "error"
    hot_tier_size: int = 0
    hash_index_size: int = 0
    qdrant_connected: bool = False
    fastembed_connected: bool = False
    hot_tier_hit_rate: float = 0.0
    avg_hash_candidates: float = 0.0
    uptime_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "tiers": {
                "hot": {
                    "size": self.hot_tier_size,
                    "hit_rate": round(self.hot_tier_hit_rate, 4),
                },
                "hash": {
                    "size": self.hash_index_size,
                    "avg_candidates": round(self.avg_hash_candidates, 2),
                },
                "vector": {
                    "qdrant_connected": self.qdrant_connected,
                    "fastembed_connected": self.fastembed_connected,
                },
            },
            "uptime_seconds": round(self.uptime_seconds, 1),
            "errors": self.errors,
        }
