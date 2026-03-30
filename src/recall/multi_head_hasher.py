"""
Engram Memory — Multi-Head Hasher
==================================
Locality-Sensitive Hashing with multiple independent hash tables
for O(1) candidate retrieval from the Matryoshka fast-slice.

Each "head" is an independent random projection that maps the
64-dim fast-slice to a binary signature. A query hits all heads
simultaneously — the union of matched buckets forms the candidate
set. Collisions on one head are triangulated away by the others.

Community Edition: 4 heads, 12-bit hash.
Cloud Edition: 8+ heads, 16-bit hash, adaptive sizing, collision analytics.

Inspired by:
- DeepSeek Engram (Jan 2026) — Multi-Head Conditional Memory
- LSH literature (Indyk & Motwani, 1998)
"""

import numpy as np
import pickle
import os
import time
import logging
from collections import defaultdict
from typing import List, Set, Dict, Optional, Tuple, Union
from dataclasses import dataclass, field

from matryoshka import get_fast_slice, SLICE_FAST

logger = logging.getLogger("engram.hasher")

# Community Edition limits
COMMUNITY_MAX_HEADS = 4
COMMUNITY_MAX_HASH_SIZE = 12


@dataclass
class HasherStats:
    """Tracks hashing performance metrics."""
    total_indexed: int = 0
    total_searches: int = 0
    total_candidates_returned: int = 0
    avg_candidates_per_search: float = 0.0
    bucket_counts: Dict[int, int] = field(default_factory=dict)
    last_rebuild: float = 0.0

    def record_search(self, num_candidates: int):
        self.total_searches += 1
        self.total_candidates_returned += num_candidates
        if self.total_searches > 0:
            self.avg_candidates_per_search = (
                self.total_candidates_returned / self.total_searches
            )


class EngramMultiHeadHasher:
    """
    Multi-Head Locality-Sensitive Hashing for O(1) memory retrieval.

    Uses random hyperplane projections to map vectors to binary
    signatures. Multiple independent "heads" ensure that even if
    one head produces a collision, the others triangulate the
    correct memory.

    Usage:
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12)
        hasher.index(vector, "doc_123")
        candidates = hasher.search_candidates(query_vector)
    """

    def __init__(
        self,
        dim: int = SLICE_FAST,
        num_heads: int = COMMUNITY_MAX_HEADS,
        hash_size: int = COMMUNITY_MAX_HASH_SIZE,
        seed: Optional[int] = None
    ):
        """
        Args:
            dim: Dimension of input vectors (should match Matryoshka fast-slice).
            num_heads: Number of independent hash tables.
                       More heads = fewer false positives, more memory.
                       Community: max 4. Cloud: 8+.
            hash_size: Number of bits per hash signature.
                       More bits = fewer collisions per bucket, but sparser tables.
                       Community: max 12. Cloud: 16+.
            seed: Random seed for reproducible projections.
        """
        # Enforce community limits
        self.dim = dim
        self.num_heads = min(num_heads, COMMUNITY_MAX_HEADS)
        self.hash_size = min(hash_size, COMMUNITY_MAX_HASH_SIZE)

        if num_heads > COMMUNITY_MAX_HEADS:
            logger.warning(
                f"Community Edition supports max {COMMUNITY_MAX_HEADS} heads. "
                f"Requested {num_heads}, clamped to {COMMUNITY_MAX_HEADS}. "
                f"Upgrade to Engram Cloud for 8+ heads with auto-tuning."
            )

        if hash_size > COMMUNITY_MAX_HASH_SIZE:
            logger.warning(
                f"Community Edition supports max {COMMUNITY_MAX_HASH_SIZE}-bit hash. "
                f"Requested {hash_size}, clamped to {COMMUNITY_MAX_HASH_SIZE}. "
                f"Upgrade to Engram Cloud for 16+ bit adaptive hashing."
            )

        # Initialize random projection matrices
        rng = np.random.RandomState(seed)
        self.projections: List[np.ndarray] = [
            rng.randn(dim, self.hash_size).astype(np.float32)
            for _ in range(self.num_heads)
        ]

        # Hash buckets: head_index -> {hash_key: [doc_ids]}
        self.buckets: List[Dict[str, List[str]]] = [
            defaultdict(list) for _ in range(self.num_heads)
        ]

        # Reverse index: doc_id -> [(head_index, hash_key)]
        # Enables O(1) removal without scanning all buckets
        self._doc_index: Dict[str, List[Tuple[int, str]]] = defaultdict(list)

        # Stats
        self.stats = HasherStats()
        self._created_at = time.time()

    def _compute_hash(self, vector: np.ndarray, head_idx: int) -> str:
        """
        Compute binary hash signature for a vector against one head.

        The projection maps the vector into hash_size dimensions.
        Each dimension's sign becomes a bit: positive → 1, negative → 0.
        The bit array is joined into a string key for dict lookup.
        """
        projection = self.projections[head_idx]
        projected = np.dot(vector, projection)
        bits = (projected > 0).astype(np.int8)
        return bits.tobytes()  # bytes key is faster than string join

    def _compute_all_hashes(self, vector: np.ndarray) -> List[str]:
        """Compute hash signatures across all heads."""
        v = np.asarray(vector[:self.dim], dtype=np.float32)
        return [self._compute_hash(v, i) for i in range(self.num_heads)]

    def index(self, vector: Union[np.ndarray, List[float]], doc_id: str) -> None:
        """
        Index a document vector into all hash tables.

        Args:
            vector: Full embedding vector (will be sliced to fast dims).
            doc_id: Unique document/memory identifier.
        """
        vec = np.asarray(vector, dtype=np.float32)
        fast_vec = vec[:self.dim]
        hashes = self._compute_all_hashes(fast_vec)

        # Remove old entries if re-indexing same doc
        if doc_id in self._doc_index:
            self._remove_from_buckets(doc_id)

        for head_idx, hash_key in enumerate(hashes):
            self.buckets[head_idx][hash_key].append(doc_id)
            self._doc_index[doc_id].append((head_idx, hash_key))

        self.stats.total_indexed += 1

    def index_batch(
        self,
        vectors: np.ndarray,
        doc_ids: List[str]
    ) -> int:
        """
        Batch index multiple vectors. Returns count indexed.

        Args:
            vectors: (N, dim) matrix of vectors.
            doc_ids: List of N document IDs.
        """
        if len(vectors) != len(doc_ids):
            raise ValueError(
                f"vectors ({len(vectors)}) and doc_ids ({len(doc_ids)}) "
                f"must have same length"
            )

        count = 0
        for vec, doc_id in zip(vectors, doc_ids):
            self.index(vec, doc_id)
            count += 1

        return count

    def search_candidates(
        self,
        query_vector: Union[np.ndarray, List[float]],
        min_heads: int = 1
    ) -> List[str]:
        """
        Find candidate document IDs via hash lookup.

        This is O(1) per head — total cost is O(num_heads).
        Returns the union of all matching buckets across all heads.

        Args:
            query_vector: Query embedding (will be sliced to fast dims).
            min_heads: Minimum number of heads that must agree.
                       1 = high recall (union). num_heads = high precision.
                       Default 1 for maximum recall; re-rank handles precision.

        Returns:
            List of candidate doc_ids (unordered, deduplicated).
        """
        vec = np.asarray(query_vector, dtype=np.float32)
        fast_vec = vec[:self.dim]
        hashes = self._compute_all_hashes(fast_vec)

        if min_heads <= 1:
            # Union mode: any head match counts (high recall)
            candidates: Set[str] = set()
            for head_idx, hash_key in enumerate(hashes):
                bucket = self.buckets[head_idx].get(hash_key, [])
                candidates.update(bucket)
        else:
            # Intersection mode: require multiple head agreement
            from collections import Counter
            vote_counts: Counter = Counter()
            for head_idx, hash_key in enumerate(hashes):
                bucket = self.buckets[head_idx].get(hash_key, [])
                for doc_id in bucket:
                    vote_counts[doc_id] += 1
            candidates = {
                doc_id for doc_id, count in vote_counts.items()
                if count >= min_heads
            }

        result = list(candidates)
        self.stats.record_search(len(result))
        return result

    def remove(self, doc_id: str) -> bool:
        """
        Remove a document from all hash tables.

        Returns True if the document was found and removed.
        """
        if doc_id not in self._doc_index:
            return False
        self._remove_from_buckets(doc_id)
        return True

    def _remove_from_buckets(self, doc_id: str) -> None:
        """Internal: remove doc_id from all its known bucket locations."""
        locations = self._doc_index.pop(doc_id, [])
        for head_idx, hash_key in locations:
            bucket = self.buckets[head_idx].get(hash_key, [])
            try:
                bucket.remove(doc_id)
                # Clean up empty buckets to save memory
                if not bucket:
                    del self.buckets[head_idx][hash_key]
            except ValueError:
                pass  # Already removed (shouldn't happen, but defensive)

    def contains(self, doc_id: str) -> bool:
        """Check if a document is currently indexed."""
        return doc_id in self._doc_index

    @property
    def size(self) -> int:
        """Number of unique documents indexed."""
        return len(self._doc_index)

    def get_bucket_distribution(self) -> Dict[int, Dict[str, int]]:
        """
        Returns bucket size distribution per head.
        Useful for diagnosing collision rates.

        Cloud-only in production; exposed here for development.
        """
        distribution = {}
        for head_idx in range(self.num_heads):
            sizes = [len(v) for v in self.buckets[head_idx].values()]
            if sizes:
                distribution[head_idx] = {
                    "num_buckets": len(sizes),
                    "avg_bucket_size": round(sum(sizes) / len(sizes), 2),
                    "max_bucket_size": max(sizes),
                    "min_bucket_size": min(sizes),
                    "total_entries": sum(sizes),
                }
            else:
                distribution[head_idx] = {
                    "num_buckets": 0,
                    "avg_bucket_size": 0,
                    "max_bucket_size": 0,
                    "min_bucket_size": 0,
                    "total_entries": 0,
                }
        return distribution

    def get_stats(self) -> dict:
        """Return current performance stats."""
        return {
            "total_indexed": self.stats.total_indexed,
            "unique_docs": self.size,
            "total_searches": self.stats.total_searches,
            "avg_candidates_per_search": round(
                self.stats.avg_candidates_per_search, 2
            ),
            "num_heads": self.num_heads,
            "hash_size": self.hash_size,
            "dim": self.dim,
            "created_at": self._created_at,
        }

    # --- Persistence ---

    def save(self, path: str) -> None:
        """
        Save hash tables and projections to disk.

        Saves everything needed to restore the hasher without
        re-indexing from Qdrant.
        """
        state = {
            "version": 1,
            "dim": self.dim,
            "num_heads": self.num_heads,
            "hash_size": self.hash_size,
            "projections": [p.tolist() for p in self.projections],
            "buckets": [dict(b) for b in self.buckets],
            "doc_index": dict(self._doc_index),
            "stats": {
                "total_indexed": self.stats.total_indexed,
                "total_searches": self.stats.total_searches,
            },
            "saved_at": time.time(),
        }

        # Atomic write: write to temp, then rename
        tmp_path = path + ".tmp"
        with open(tmp_path, "wb") as f:
            pickle.dump(state, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp_path, path)

        logger.info(
            f"Saved hash index: {self.size} docs, "
            f"{self.num_heads} heads, {path}"
        )

    @classmethod
    def load(cls, path: str) -> "EngramMultiHeadHasher":
        """
        Load a saved hasher from disk.

        The projection matrices are restored exactly, so hash
        signatures will match the original indexing.
        """
        with open(path, "rb") as f:
            state = pickle.load(f)

        version = state.get("version", 0)
        if version != 1:
            raise ValueError(f"Unsupported hash index version: {version}")

        hasher = cls(
            dim=state["dim"],
            num_heads=state["num_heads"],
            hash_size=state["hash_size"],
        )

        # Restore projections (must match original for consistent hashing)
        hasher.projections = [
            np.array(p, dtype=np.float32) for p in state["projections"]
        ]

        # Restore buckets
        hasher.buckets = [
            defaultdict(list, b) for b in state["buckets"]
        ]

        # Restore reverse index
        hasher._doc_index = defaultdict(list)
        for doc_id, locations in state["doc_index"].items():
            hasher._doc_index[doc_id] = [
                (loc[0], loc[1]) if isinstance(loc, (list, tuple)) else loc
                for loc in locations
            ]

        # Restore stats
        hasher.stats.total_indexed = state.get("stats", {}).get(
            "total_indexed", hasher.size
        )
        hasher.stats.total_searches = state.get("stats", {}).get(
            "total_searches", 0
        )
        hasher.stats.last_rebuild = state.get("saved_at", time.time())

        logger.info(
            f"Loaded hash index: {hasher.size} docs, "
            f"{hasher.num_heads} heads from {path}"
        )

        return hasher

    def rebuild_from_vectors(
        self,
        vectors: np.ndarray,
        doc_ids: List[str]
    ) -> int:
        """
        Rebuild the entire hash index from scratch.

        Call this if the hash file is corrupted, or after changing
        num_heads / hash_size configuration.

        Args:
            vectors: (N, full_dim) matrix — will be sliced internally.
            doc_ids: Corresponding document IDs.

        Returns:
            Number of documents indexed.
        """
        # Clear everything
        self.buckets = [defaultdict(list) for _ in range(self.num_heads)]
        self._doc_index = defaultdict(list)
        self.stats = HasherStats()
        self.stats.last_rebuild = time.time()

        count = self.index_batch(vectors, doc_ids)
        logger.info(f"Rebuilt hash index: {count} docs indexed")
        return count
