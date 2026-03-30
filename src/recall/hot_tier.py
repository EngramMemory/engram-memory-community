"""
Engram Memory — Hot-Tier Frequency Cache
==========================================
Sub-millisecond recall for frequently accessed memories.

Uses frequency-adjusted exponential decay (Ebbinghaus model):
    Strength = log(hits + 1) × e^(-λ × hours_since_access)

Memories that are accessed often stay "hot." Memories that haven't
been touched decay naturally and get evicted to make room for new
hot memories. This mimics Long-Term Potentiation in biological brains.

Community Edition: Max 1000 entries, single instance, basic decay.
Cloud Edition: Unlimited, distributed, per-user adaptive λ, analytics.
"""

import time
import math
import json
import os
import logging
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field

import numpy as np

from matryoshka import cosine_similarity, normalize

logger = logging.getLogger("engram.hot_tier")

# Community Edition limits
COMMUNITY_MAX_SIZE = 1000


@dataclass
class HotMemory:
    """A single memory entry in the hot-tier cache."""
    doc_id: str
    vector: np.ndarray        # Full vector for similarity comparison
    content: str              # Original text (for context injection)
    category: str             # preference, fact, decision, entity, other
    hits: int                 # Total access count
    last_access: float        # Unix timestamp of last access
    first_access: float       # Unix timestamp of first cache entry
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "vector": self.vector.tolist(),
            "content": self.content,
            "category": self.category,
            "hits": self.hits,
            "last_access": self.last_access,
            "first_access": self.first_access,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HotMemory":
        return cls(
            doc_id=d["doc_id"],
            vector=np.array(d["vector"], dtype=np.float32),
            content=d["content"],
            category=d["category"],
            hits=d["hits"],
            last_access=d["last_access"],
            first_access=d["first_access"],
            metadata=d.get("metadata", {}),
        )


@dataclass
class HotTierStats:
    """Performance counters for the hot-tier cache."""
    total_hits: int = 0          # Queries answered by hot-tier
    total_misses: int = 0        # Queries that fell through
    total_evictions: int = 0     # Entries evicted due to capacity
    total_upserts: int = 0       # Entries added or updated
    total_decayed: int = 0       # Entries removed by decay sweep

    @property
    def hit_rate(self) -> float:
        total = self.total_hits + self.total_misses
        return self.total_hits / total if total > 0 else 0.0


class EngramHotTier:
    """
    Frequency-adjusted exponential decay cache for instant recall.

    The hot-tier sits in front of the hash index and vector store.
    When a query comes in, the hot-tier is checked first. If a
    cached memory has high similarity AND high strength (frequent
    access, recent), it's returned immediately — zero latency.

    The biological model:
    - Accessing a memory strengthens it (hit count goes up)
    - Not accessing it causes decay (exponential time-based)
    - When the cache is full, the weakest memory is evicted
    - The result: your AI "remembers" what matters to YOU

    Usage:
        hot = EngramHotTier(max_size=1000, decay_rate=0.1)

        # On successful retrieval from any tier:
        hot.upsert("doc_123", vector, "User prefers TypeScript", "preference")

        # Before searching hash/vector tiers:
        results = hot.search(query_vector, top_k=3, min_similarity=0.7)
        if results:
            return results  # Sub-millisecond, skip everything else
    """

    def __init__(
        self,
        max_size: int = COMMUNITY_MAX_SIZE,
        decay_rate: float = 0.1,
        similarity_threshold: float = 0.70
    ):
        """
        Args:
            max_size: Maximum cached memories.
                      Community: capped at 1000.
                      Cloud: unlimited.
            decay_rate: Lambda (λ) for exponential decay.
                        Higher = memories fade faster.
                        0.1 = memory at 50% strength after ~7 hours of no access.
                        Community: fixed.
                        Cloud: adaptive per-user learning.
            similarity_threshold: Minimum cosine similarity for a cache hit.
        """
        self.max_size = min(max_size, COMMUNITY_MAX_SIZE)
        self.decay_rate = decay_rate
        self.similarity_threshold = similarity_threshold

        if max_size > COMMUNITY_MAX_SIZE:
            logger.warning(
                f"Community Edition supports max {COMMUNITY_MAX_SIZE} hot-tier entries. "
                f"Requested {max_size}, clamped to {COMMUNITY_MAX_SIZE}. "
                f"Upgrade to Engram Cloud for unlimited hot-tier with "
                f"distributed sync and adaptive decay."
            )

        # Storage: doc_id -> HotMemory
        self._cache: Dict[str, HotMemory] = {}

        # Pre-computed matrix for batch similarity (rebuilt on change)
        self._matrix_dirty: bool = True
        self._vector_matrix: Optional[np.ndarray] = None
        self._matrix_ids: List[str] = []

        # Stats
        self.stats = HotTierStats()

    def _calculate_strength(self, entry: HotMemory) -> float:
        """
        Calculate current memory strength using Ebbinghaus decay.

        Strength = log(hits + 1) × e^(-λ × hours_since_access)

        This means:
        - A memory accessed 100 times has ~4.6x the base strength of one accessed once
        - A memory not accessed for 10 hours at λ=0.1 retains ~37% of its strength
        - The combination rewards both frequency AND recency
        """
        hours_elapsed = (time.time() - entry.last_access) / 3600.0
        strength = math.log1p(entry.hits) * math.exp(
            -self.decay_rate * hours_elapsed
        )
        return strength

    def _rebuild_matrix(self) -> None:
        """Rebuild the pre-computed vector matrix for batch similarity."""
        if not self._cache:
            self._vector_matrix = None
            self._matrix_ids = []
            self._matrix_dirty = False
            return

        self._matrix_ids = list(self._cache.keys())
        vectors = [self._cache[doc_id].vector for doc_id in self._matrix_ids]
        self._vector_matrix = np.vstack(vectors).astype(np.float32)
        self._matrix_dirty = False

    def upsert(
        self,
        doc_id: str,
        vector: Union[np.ndarray, List[float]],
        content: str = "",
        category: str = "other",
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add or update a memory in the hot-tier.

        If the memory already exists, increment its hit count and
        refresh its last_access timestamp (strengthening it).

        If the cache is full, evict the weakest memory first.

        Args:
            doc_id: Unique memory identifier.
            vector: Full embedding vector (stored for similarity matching).
            content: Original text content.
            category: Memory category.
            metadata: Optional metadata dict.
        """
        vec = np.asarray(vector, dtype=np.float32)
        now = time.time()

        if doc_id in self._cache:
            # Strengthen existing memory
            entry = self._cache[doc_id]
            entry.hits += 1
            entry.last_access = now
            entry.vector = vec  # Update in case vector was re-embedded
            if content:
                entry.content = content
            if metadata:
                entry.metadata.update(metadata)
        else:
            # Evict weakest if at capacity
            if len(self._cache) >= self.max_size:
                self._evict_weakest()

            self._cache[doc_id] = HotMemory(
                doc_id=doc_id,
                vector=vec,
                content=content,
                category=category,
                hits=1,
                last_access=now,
                first_access=now,
                metadata=metadata or {},
            )
            self._matrix_dirty = True

        self.stats.total_upserts += 1

    def search(
        self,
        query_vector: Union[np.ndarray, List[float]],
        top_k: int = 5,
        min_similarity: Optional[float] = None,
        min_strength: float = 0.1
    ) -> List[Tuple[str, float, float]]:
        """
        Search the hot-tier cache for matching memories.

        Returns memories that are both semantically similar AND
        sufficiently "strong" (recently/frequently accessed).

        Args:
            query_vector: Query embedding vector.
            top_k: Maximum results to return.
            min_similarity: Minimum cosine similarity (default: self.similarity_threshold).
            min_strength: Minimum Ebbinghaus strength score.

        Returns:
            List of (doc_id, similarity, strength) tuples, sorted by
            combined score (similarity × strength).
        """
        if not self._cache:
            self.stats.total_misses += 1
            return []

        threshold = min_similarity or self.similarity_threshold
        query = np.asarray(query_vector, dtype=np.float32)

        # Rebuild matrix if cache changed
        if self._matrix_dirty:
            self._rebuild_matrix()

        if self._vector_matrix is None or len(self._matrix_ids) == 0:
            self.stats.total_misses += 1
            return []

        # Batch cosine similarity against all cached vectors
        q_norm = np.linalg.norm(query)
        if q_norm == 0:
            self.stats.total_misses += 1
            return []

        q = query / q_norm
        norms = np.linalg.norm(self._vector_matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        normed = self._vector_matrix / norms
        similarities = normed @ q

        # Filter and score
        results = []
        for i, doc_id in enumerate(self._matrix_ids):
            sim = float(similarities[i])
            if sim < threshold:
                continue

            entry = self._cache.get(doc_id)
            if entry is None:
                continue

            strength = self._calculate_strength(entry)
            if strength < min_strength:
                continue

            # Combined score: similarity weighted by memory strength
            combined = sim * (1.0 + math.log1p(strength))
            results.append((doc_id, sim, strength, combined))

        if not results:
            self.stats.total_misses += 1
            return []

        # Sort by combined score, take top_k
        results.sort(key=lambda x: x[3], reverse=True)
        top_results = [(r[0], r[1], r[2]) for r in results[:top_k]]

        # Update access timestamps for returned memories (reinforcement)
        now = time.time()
        for doc_id, _, _ in top_results:
            if doc_id in self._cache:
                self._cache[doc_id].hits += 1
                self._cache[doc_id].last_access = now

        self.stats.total_hits += 1
        return top_results

    def get_memory(self, doc_id: str) -> Optional[HotMemory]:
        """Get a specific memory by ID (without incrementing hits)."""
        return self._cache.get(doc_id)

    def get_content(self, doc_id: str) -> Optional[str]:
        """Get the text content of a cached memory."""
        entry = self._cache.get(doc_id)
        return entry.content if entry else None

    def _evict_weakest(self) -> None:
        """Remove the memory with the lowest current strength."""
        if not self._cache:
            return

        weakest_id = min(
            self._cache.keys(),
            key=lambda doc_id: self._calculate_strength(self._cache[doc_id])
        )

        del self._cache[weakest_id]
        self._matrix_dirty = True
        self.stats.total_evictions += 1

        logger.debug(f"Evicted weakest memory: {weakest_id}")

    def decay_sweep(self, min_strength: float = 0.01) -> int:
        """
        Remove all memories below the minimum strength threshold.

        Call this periodically (e.g., every hour) to clean out
        memories that have fully decayed.

        Returns:
            Number of memories removed.
        """
        to_remove = []
        for doc_id, entry in self._cache.items():
            if self._calculate_strength(entry) < min_strength:
                to_remove.append(doc_id)

        for doc_id in to_remove:
            del self._cache[doc_id]

        if to_remove:
            self._matrix_dirty = True
            self.stats.total_decayed += len(to_remove)
            logger.info(f"Decay sweep removed {len(to_remove)} memories")

        return len(to_remove)

    def remove(self, doc_id: str) -> bool:
        """Explicitly remove a memory from the hot-tier."""
        if doc_id in self._cache:
            del self._cache[doc_id]
            self._matrix_dirty = True
            return True
        return False

    def get_top_memories(self, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        Get the strongest memories currently in cache.

        Returns:
            List of (doc_id, strength) sorted by strength descending.
        """
        scored = [
            (doc_id, self._calculate_strength(entry))
            for doc_id, entry in self._cache.items()
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get_context_injection(self, top_k: int = 5) -> str:
        """
        Format the top hot memories for injection into an LLM system prompt.

        This is the "Context Injection" killer feature — the strongest
        memories are automatically prepended to the agent's context.

        Returns:
            Formatted string ready for system prompt injection.
        """
        top = self.get_top_memories(top_k)
        if not top:
            return ""

        lines = ["[HOT MEMORIES — Auto-injected from Engram Hot-Tier]"]
        for doc_id, strength in top:
            entry = self._cache.get(doc_id)
            if entry:
                lines.append(
                    f"• [{entry.category.upper()}] {entry.content} "
                    f"(strength: {strength:.2f}, hits: {entry.hits})"
                )
        lines.append("[END HOT MEMORIES]")
        return "\n".join(lines)

    @property
    def size(self) -> int:
        """Number of memories currently cached."""
        return len(self._cache)

    def get_stats(self) -> dict:
        """Return performance metrics."""
        return {
            "size": self.size,
            "max_size": self.max_size,
            "hit_rate": round(self.stats.hit_rate, 4),
            "total_hits": self.stats.total_hits,
            "total_misses": self.stats.total_misses,
            "total_evictions": self.stats.total_evictions,
            "total_upserts": self.stats.total_upserts,
            "total_decayed": self.stats.total_decayed,
            "decay_rate": self.decay_rate,
            "similarity_threshold": self.similarity_threshold,
        }

    # --- Persistence ---

    def save(self, path: str) -> None:
        """Save cache to disk as JSON."""
        state = {
            "version": 1,
            "max_size": self.max_size,
            "decay_rate": self.decay_rate,
            "similarity_threshold": self.similarity_threshold,
            "entries": {
                doc_id: entry.to_dict()
                for doc_id, entry in self._cache.items()
            },
            "stats": {
                "total_hits": self.stats.total_hits,
                "total_misses": self.stats.total_misses,
                "total_evictions": self.stats.total_evictions,
                "total_upserts": self.stats.total_upserts,
                "total_decayed": self.stats.total_decayed,
            },
            "saved_at": time.time(),
        }

        tmp_path = path + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(state, f)
        os.replace(tmp_path, path)

        logger.info(f"Saved hot-tier: {self.size} entries to {path}")

    @classmethod
    def load(cls, path: str) -> "EngramHotTier":
        """Load cache from disk."""
        with open(path, "r") as f:
            state = json.load(f)

        version = state.get("version", 0)
        if version != 1:
            raise ValueError(f"Unsupported hot-tier version: {version}")

        hot = cls(
            max_size=state["max_size"],
            decay_rate=state["decay_rate"],
            similarity_threshold=state.get("similarity_threshold", 0.70),
        )

        for doc_id, entry_dict in state.get("entries", {}).items():
            entry = HotMemory.from_dict(entry_dict)
            # Drop entries with empty content (from pre-fix cache)
            if not entry.content:
                continue
            hot._cache[doc_id] = entry

        stats = state.get("stats", {})
        hot.stats.total_hits = stats.get("total_hits", 0)
        hot.stats.total_misses = stats.get("total_misses", 0)
        hot.stats.total_evictions = stats.get("total_evictions", 0)
        hot.stats.total_upserts = stats.get("total_upserts", 0)
        hot.stats.total_decayed = stats.get("total_decayed", 0)

        hot._matrix_dirty = True

        logger.info(f"Loaded hot-tier: {hot.size} entries from {path}")
        return hot
