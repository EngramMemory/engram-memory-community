"""
Engram Memory — Recall Engine
===============================
The unified three-tiered retrieval pipeline.

Query flow:
    1. HOT-TIER CHECK  → Sub-ms frequency cache lookup
    2. HASH LOOKUP     → O(1) LSH candidate retrieval
    3. VECTOR RE-RANK  → Full cosine similarity on candidates (or fallback)

This class replaces the flat `memory_search.py` with a tiered system
that gets faster the more you use it.

Usage:
    engine = EngramRecallEngine(config)
    await engine.warmup()

    # Store
    doc_id = await engine.store("User prefers TypeScript", category="preference")

    # Search (automatically uses best tier)
    results = await engine.search("language preferences", top_k=5)

    # Shutdown (persist state)
    await engine.shutdown()
"""

import hashlib
import math
import os
import re
import time
import asyncio
import logging
from collections import Counter
from typing import List, Optional, Dict, Union

import numpy as np
import httpx

from matryoshka import (
    get_fast_slice,
    get_full_vector,
    cosine_similarity,
    batch_cosine_similarity,
    validate_vector,
    SLICE_FULL,
)
from multi_head_hasher import EngramMultiHeadHasher
from hot_tier import EngramHotTier
from models import MemoryResult, EngramConfig, RecallEngineHealth

logger = logging.getLogger("engram.engine")

# ─── BM25 Sparse Vectors ────────────────────────────────────────────
# Hash-based tokenization: no global vocabulary needed, deterministic,
# works independently across local and cloud deployments.

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "to", "of", "in", "for", "on",
    "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "between", "out", "off", "over", "under", "then",
    "here", "there", "when", "where", "why", "how", "all", "each",
    "both", "more", "most", "other", "some", "no", "not", "only",
    "so", "than", "too", "very", "just", "but", "and", "or", "if",
    "that", "this", "it", "its", "i", "me", "my", "we", "our", "you",
    "your", "he", "him", "his", "she", "her", "they", "them", "their",
    "what", "which", "who",
})


def text_to_sparse_vector(text: str, boost_specifics: bool = False) -> Dict:
    """Convert text to a sparse vector for Qdrant hybrid search.

    Uses hash-based tokenization with unigrams + bigrams.
    No shared vocabulary needed — each token hashes to a stable uint32 index.
    boost_specifics=True weights numbers/versions higher (use at store time).
    """
    # Keep version strings like "16.2" as single tokens
    tokens = re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", text.lower())
    tokens = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    if not tokens:
        return {"indices": [], "values": []}

    tf = Counter(tokens)

    # Bigrams: "postgresql 16.2" and "github actions" as single entries
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]} {tokens[i+1]}"
        tf[bigram] = tf.get(bigram, 0) + 1

    indices = []
    values = []
    for token, count in tf.items():
        idx = int(hashlib.md5(token.encode()).hexdigest()[:8], 16) & 0x3FFFFFFF
        weight = 1.0 + math.log(count) if count > 1 else 1.0
        if boost_specifics and re.match(r"^[0-9]", token):
            weight *= 1.5
        indices.append(idx)
        values.append(round(weight, 4))
    return {"indices": indices, "values": values}


class EngramRecallEngine:
    """
    Three-Tiered Brain for AI memory retrieval.

    Tier 1: Hot-Tier Cache (sub-millisecond)
        Frequency-adjusted decay cache. Memories that are accessed
        often stay hot. Zero search cost.

    Tier 2: Multi-Head Hash Index (O(1))
        LSH with 4 independent heads. Maps 64-dim fast-slice to
        binary signature for instant candidate retrieval.

    Tier 3: Full Vector Re-Rank (standard)
        Qdrant ANN search on the full 768-dim vector. Only used
        as fallback when Tiers 1+2 miss, or to re-rank hash candidates.
    """

    def __init__(self, config: Optional[EngramConfig] = None):
        self.config = config or EngramConfig()
        self.config.ensure_data_dir()

        # Initialize tiers
        self.hot_tier = EngramHotTier(
            max_size=self.config.hot_tier_max_size,
            decay_rate=self.config.hot_tier_decay_rate,
            similarity_threshold=self.config.hot_tier_similarity_threshold,
        )

        self.hasher = EngramMultiHeadHasher(
            dim=self.config.fast_dim,
            num_heads=self.config.hasher_num_heads,
            hash_size=self.config.hasher_hash_size,
            seed=self.config.hasher_seed,
        )

        # HTTP client for FastEmbed + Qdrant
        self._http: Optional[httpx.AsyncClient] = None

        # Lifecycle
        self._started_at: float = 0.0
        self._persist_task: Optional[asyncio.Task] = None
        self._sweep_task: Optional[asyncio.Task] = None

    # --- Lifecycle ---

    async def warmup(self) -> None:
        """
        Initialize the engine: load persisted state, connect to services.

        Call this once at startup before any search/store operations.
        """
        self._started_at = time.time()
        self._http = httpx.AsyncClient(timeout=30.0)

        # Load persisted hot-tier
        hot_path = os.path.join(
            self.config.data_dir, "hot_tier.json"
        )
        if os.path.exists(hot_path):
            try:
                self.hot_tier = EngramHotTier.load(hot_path)
                logger.info(
                    f"Restored hot-tier: {self.hot_tier.size} entries"
                )
            except Exception as e:
                logger.warning(f"Failed to load hot-tier, starting fresh: {e}")

        # Load persisted hash index
        hash_path = os.path.join(
            self.config.data_dir, "hash_index.pkl"
        )
        if os.path.exists(hash_path):
            try:
                self.hasher = EngramMultiHeadHasher.load(hash_path)
                logger.info(
                    f"Restored hash index: {self.hasher.size} docs"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load hash index, starting fresh: {e}"
                )

        # Start background tasks
        if self.config.auto_persist:
            self._persist_task = asyncio.create_task(
                self._auto_persist_loop()
            )
        self._sweep_task = asyncio.create_task(
            self._decay_sweep_loop()
        )

        logger.info("Engram Recall Engine started (Three-Tiered Brain)")

    async def shutdown(self) -> None:
        """Persist state and clean up."""
        # Cancel background tasks
        if self._persist_task:
            self._persist_task.cancel()
        if self._sweep_task:
            self._sweep_task.cancel()

        # Persist state
        await self._persist()

        # Close HTTP client
        if self._http:
            await self._http.aclose()

        logger.info("Engram Recall Engine stopped")

    async def _persist(self) -> None:
        """Save hot-tier and hash index to disk."""
        try:
            hot_path = os.path.join(self.config.data_dir, "hot_tier.json")
            self.hot_tier.save(hot_path)

            hash_path = os.path.join(self.config.data_dir, "hash_index.pkl")
            self.hasher.save(hash_path)
        except Exception as e:
            logger.error(f"Failed to persist state: {e}")

    async def _auto_persist_loop(self) -> None:
        """Background task: auto-persist every N seconds."""
        while True:
            try:
                await asyncio.sleep(self.config.persist_interval)
                await self._persist()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-persist error: {e}")

    async def _decay_sweep_loop(self) -> None:
        """Background task: sweep decayed memories from hot-tier."""
        while True:
            try:
                await asyncio.sleep(self.config.hot_tier_sweep_interval)
                removed = self.hot_tier.decay_sweep()
                if removed > 0:
                    logger.info(f"Decay sweep removed {removed} memories")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Decay sweep error: {e}")

    # --- Embedding ---

    async def _embed(self, text: str, type: str = None) -> np.ndarray:
        """
        Generate embedding via local FastEmbed service.

        Args:
            text: Text to embed.
            type: "document" for storage, "query" for search.
                  Adds nomic-embed-text-v1.5 task prefixes for better recall.

        Returns full-dimension vector (768 for nomic-embed-text-v1.5).
        """
        if not self._http:
            raise RuntimeError("Engine not started. Call warmup() first.")

        body = {"texts": [text]}
        if type:
            body["type"] = type

        response = await self._http.post(
            f"{self.config.embedding_url}/embeddings",
            json=body,
        )
        response.raise_for_status()
        data = response.json()

        # FastEmbed service returns {"embeddings": [[...]]}
        vec = np.array(data["embeddings"][0], dtype=np.float32)

        is_valid, msg = validate_vector(vec, self.config.embedding_dim)
        if not is_valid:
            raise ValueError(f"Invalid embedding: {msg}")

        return vec

    # --- Store ---

    async def store(
        self,
        content: str,
        category: str = "other",
        metadata: Optional[Dict] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        """
        Store a memory across all tiers.

        1. Generate embedding via FastEmbed
        2. Store full vector in Qdrant (Tier 3)
        3. Index fast-slice in Multi-Head Hasher (Tier 2)
        4. (Hot-tier is populated on retrieval, not on store)

        Args:
            content: The text to remember.
            category: Auto-detected or specified category.
            metadata: Optional key-value metadata.
            doc_id: Optional explicit ID (auto-generated if None).

        Returns:
            The document ID.
        """
        import uuid

        if not self._http:
            raise RuntimeError("Engine not started. Call warmup() first.")

        # Generate ID
        if doc_id is None:
            doc_id = str(uuid.uuid4())

        # Embed (document prefix for storage)
        vector = await self._embed(content, type="document")

        # Generate sparse vector for hybrid search
        sparse = text_to_sparse_vector(content, boost_specifics=True)

        # Store in Qdrant (Tier 3) — named vectors for hybrid search
        payload = {
            "text": content,
            "content": content,
            "category": category,
            "created_at": time.time(),
            "access_count": 0,
            **(metadata or {}),
        }

        await self._http.put(
            f"{self.config.qdrant_url}/collections/{self.config.collection}/points",
            json={
                "points": [
                    {
                        "id": doc_id,
                        "vector": {
                            "dense": vector.tolist(),
                            "bm25": sparse,
                        },
                        "payload": payload,
                    }
                ]
            },
        )

        # Index in Multi-Head Hasher (Tier 2)
        self.hasher.index(vector, doc_id)

        logger.debug(f"Stored memory {doc_id}: {content[:80]}...")
        return doc_id

    # --- Search (The Three-Tiered Pipeline) ---

    async def search(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
    ) -> List[MemoryResult]:
        """
        Search for memories using the three-tiered brain.

        Tier 1 (Hot-Tier): Check frequency cache first.
            If sufficient results found → return immediately.

        Tier 2 (Hash): O(1) candidate lookup via LSH.
            Get candidate IDs → fetch from Qdrant by ID → re-rank.

        Tier 3 (Vector): Full ANN search on Qdrant.
            Fallback when Tiers 1+2 don't produce enough results.

        Args:
            query: Natural language search query.
            top_k: Maximum number of results.
            category: Optional filter by memory category.

        Returns:
            List of MemoryResult, sorted by relevance, tagged with tier.
        """
        if not self._http:
            raise RuntimeError("Engine not started. Call warmup() first.")

        # Embed the query (query prefix for search)
        query_vector = await self._embed(query, type="query")
        results: List[MemoryResult] = []

        # ── TIER 1: Hot-Tier Cache ──
        hot_results = self.hot_tier.search(
            query_vector,
            top_k=top_k,
            min_similarity=self.config.hot_tier_similarity_threshold,
        )

        for doc_id, similarity, strength in hot_results:
            entry = self.hot_tier.get_memory(doc_id)
            if entry is None:
                continue
            if category and entry.category != category:
                continue

            results.append(MemoryResult(
                doc_id=doc_id,
                content=entry.content,
                score=similarity + min(strength * 0.05, 0.1),
                tier="hot",
                category=entry.category,
                metadata=entry.metadata,
                access_count=entry.hits,
                strength=strength,
                similarity=similarity,
            ))

        # If hot-tier gave us enough, return early
        if len(results) >= top_k:
            logger.debug(
                f"Hot-tier hit: {len(results)} results for '{query[:50]}'"
            )
            return results[:top_k]

        remaining = top_k - len(results)
        seen_ids = {r.doc_id for r in results}

        # ── TIER 2: Multi-Head Hash Index ──
        candidate_ids = self.hasher.search_candidates(query_vector)

        # Filter out already-seen IDs
        candidate_ids = [
            cid for cid in candidate_ids if cid not in seen_ids
        ]

        if candidate_ids:
            # Fetch candidate vectors from Qdrant by ID
            hash_results = await self._fetch_and_rerank(
                query_vector, candidate_ids, remaining, category
            )

            for result in hash_results:
                result.tier = "hash"
                results.append(result)
                seen_ids.add(result.doc_id)

                # Promote to hot-tier with actual document vector
                self.hot_tier.upsert(
                    doc_id=result.doc_id,
                    vector=result.doc_vector if result.doc_vector is not None else query_vector,
                    content=result.content,
                    category=result.category,
                    metadata=result.metadata,
                )

        # ── TIER 3: Hybrid Search (always runs) ──
        # Hybrid (dense + BM25) can find keyword matches that semantic-only misses.
        # Always run it and merge with Tier 1+2 — best scores win.
        vector_results = await self._qdrant_search(
            query_vector, top_k * 2, category, query_text=query
        )

        for result in vector_results:
            if result.doc_id in seen_ids:
                continue
            result.tier = "vector"
            results.append(result)
            seen_ids.add(result.doc_id)

            # Promote to hot-tier with actual document vector
            self.hot_tier.upsert(
                doc_id=result.doc_id,
                vector=result.doc_vector if result.doc_vector is not None else query_vector,
                content=result.content,
                category=result.category,
                metadata=result.metadata,
            )

        # Final sort by score, take top_k
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def _fetch_and_rerank(
        self,
        query_vector: np.ndarray,
        candidate_ids: List[str],
        top_k: int,
        category: Optional[str] = None,
    ) -> List[MemoryResult]:
        """
        Fetch specific points from Qdrant by ID and re-rank with full vector.
        """
        try:
            response = await self._http.post(
                f"{self.config.qdrant_url}/collections/{self.config.collection}/points",
                json={"ids": candidate_ids, "with_payload": True, "with_vector": True},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"Qdrant fetch error: {e}")
            return []

        points = data.get("result", [])
        results = []

        for point in points:
            payload = point.get("payload", {})
            point_category = payload.get("category", "other")

            if category and point_category != category:
                continue

            # Handle both named vectors (hybrid) and flat vectors (legacy)
            raw_vec = point.get("vector", {})
            if isinstance(raw_vec, dict):
                raw_vec = raw_vec.get("dense", [])
            point_vector = np.array(raw_vec, dtype=np.float32)
            if len(point_vector) == 0:
                continue

            similarity = cosine_similarity(query_vector, point_vector)

            if similarity < self.config.min_recall_score:
                continue

            results.append(MemoryResult(
                doc_id=point.get("id", ""),
                content=payload.get("content", payload.get("text", "")),
                score=float(similarity),
                tier="hash",
                category=point_category,
                metadata={
                    k: v for k, v in payload.items()
                    if k not in ("content", "category", "created_at", "access_count")
                },
                created_at=payload.get("created_at", 0),
                access_count=payload.get("access_count", 0),
                similarity=float(similarity),
                doc_vector=point_vector,
            ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    async def _qdrant_search(
        self,
        query_vector: np.ndarray,
        top_k: int,
        category: Optional[str] = None,
        query_text: Optional[str] = None,
    ) -> List[MemoryResult]:
        """
        Hybrid Qdrant search: dense vectors + BM25 sparse vectors with RRF fusion.
        Falls back to dense-only if hybrid fails (e.g., old collection without sparse vectors).
        """
        filter_clause = None
        if category:
            filter_clause = {
                "must": [
                    {"key": "category", "match": {"value": category}}
                ]
            }

        # Try hybrid search first (dense + sparse with RRF)
        if query_text:
            sparse = text_to_sparse_vector(query_text)
            if sparse["indices"]:
                query_body: Dict = {
                    "prefetch": [
                        {
                            "query": query_vector.tolist(),
                            "using": "dense",
                            "limit": top_k * 2,
                        },
                        {
                            "query": sparse,
                            "using": "bm25",
                            "limit": top_k * 4,
                        },
                    ],
                    "query": {"fusion": "rrf"},
                    "limit": top_k,
                    "with_payload": True,
                    "with_vector": True,
                }
                if filter_clause:
                    query_body["filter"] = filter_clause

                try:
                    response = await self._http.post(
                        f"{self.config.qdrant_url}/collections/{self.config.collection}/points/query",
                        json=query_body,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        return self._parse_qdrant_results(data.get("result", {}).get("points", []))
                    else:
                        logger.debug(f"Hybrid search failed ({response.status_code}), falling back to dense-only")
                except Exception as e:
                    logger.debug(f"Hybrid search error, falling back to dense-only: {e}")

        # Fallback: dense-only search (works with old collections too)
        search_body: Dict = {
            "vector": {"name": "dense", "vector": query_vector.tolist()},
            "limit": top_k,
            "with_payload": True,
            "with_vector": True,
            "score_threshold": self.config.min_recall_score,
        }

        if filter_clause:
            search_body["filter"] = filter_clause

        try:
            response = await self._http.post(
                f"{self.config.qdrant_url}/collections/{self.config.collection}/points/search",
                json=search_body,
            )
            # If named vector search fails, try flat vector (legacy collections)
            if response.status_code != 200:
                search_body["vector"] = query_vector.tolist()
                response = await self._http.post(
                    f"{self.config.qdrant_url}/collections/{self.config.collection}/points/search",
                    json=search_body,
                )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error(f"Qdrant search error: {e}")
            return []

        return self._parse_qdrant_results(data.get("result", []))

    def _parse_qdrant_results(self, hits: list) -> List[MemoryResult]:
        """Parse Qdrant search/query results into MemoryResult objects."""
        results = []
        for hit in hits:
            payload = hit.get("payload", {})
            # Extract document vector for hot-tier promotion
            raw_vec = hit.get("vector", {})
            if isinstance(raw_vec, dict):
                raw_vec = raw_vec.get("dense", [])
            doc_vec = np.array(raw_vec, dtype=np.float32) if raw_vec else None

            results.append(MemoryResult(
                doc_id=str(hit.get("id", "")),
                content=payload.get("content", payload.get("text", "")),
                score=float(hit.get("score", 0)),
                tier="vector",
                category=payload.get("category", "other"),
                metadata={
                    k: v for k, v in payload.items()
                    if k not in ("content", "category", "created_at", "access_count")
                },
                created_at=payload.get("created_at", 0),
                access_count=payload.get("access_count", 0),
                similarity=float(hit.get("score", 0)),
                doc_vector=doc_vec if doc_vec is not None and len(doc_vec) > 0 else None,
            ))
        return results

    # --- Forget ---

    async def forget(self, doc_id: str) -> bool:
        """
        Remove a memory from all tiers.

        Args:
            doc_id: The memory ID to forget.

        Returns:
            True if the memory was found and removed.
        """
        removed = False

        # Remove from hot-tier
        if self.hot_tier.remove(doc_id):
            removed = True

        # Remove from hash index
        if self.hasher.remove(doc_id):
            removed = True

        # Remove from Qdrant
        try:
            response = await self._http.post(
                f"{self.config.qdrant_url}/collections/{self.config.collection}/points/delete",
                json={"points": [doc_id]},
            )
            if response.status_code == 200:
                removed = True
            # 400/404 means point doesn't exist in Qdrant — not an error
        except Exception as e:
            logger.debug(f"Qdrant delete skipped for {doc_id}: {e}")

        if removed:
            logger.debug(f"Forgot memory: {doc_id}")

        return removed

    # --- Context Injection ---

    def get_hot_context(self, top_k: int = 5) -> str:
        """
        Get formatted hot memories for system prompt injection.

        This is the "Personalized Brain" feature — the strongest
        memories are automatically included in the agent's context.
        """
        return self.hot_tier.get_context_injection(top_k)

    # --- Health ---

    async def get_health(self) -> RecallEngineHealth:
        """Check health of all tiers."""
        health = RecallEngineHealth(status="healthy")
        health.uptime_seconds = time.time() - self._started_at

        # Hot-tier
        health.hot_tier_size = self.hot_tier.size
        health.hot_tier_hit_rate = self.hot_tier.stats.hit_rate

        # Hash index
        health.hash_index_size = self.hasher.size
        health.avg_hash_candidates = self.hasher.stats.avg_candidates_per_search

        # Qdrant connectivity
        try:
            resp = await self._http.get(
                f"{self.config.qdrant_url}/collections/{self.config.collection}"
            )
            health.qdrant_connected = resp.status_code == 200
        except Exception as e:
            health.qdrant_connected = False
            health.errors.append(f"Qdrant: {e}")

        # FastEmbed connectivity
        try:
            resp = await self._http.get(f"{self.config.embedding_url}/health")
            health.fastembed_connected = resp.status_code == 200
        except Exception as e:
            health.fastembed_connected = False
            health.errors.append(f"FastEmbed: {e}")

        if health.errors:
            health.status = "degraded"

        return health

    # --- Index Rebuild ---

    async def rebuild_hash_index(self) -> int:
        """
        Rebuild the hash index from all vectors in Qdrant.

        Use this if the hash file is corrupted or after changing
        hash configuration (num_heads, hash_size).

        Returns:
            Number of documents re-indexed.
        """
        logger.info("Rebuilding hash index from Qdrant...")

        # Scroll through all points in Qdrant
        offset = None
        all_vectors = []
        all_ids = []

        while True:
            scroll_body: Dict = {
                "limit": 100,
                "with_payload": False,
                "with_vector": True,
            }
            if offset is not None:
                scroll_body["offset"] = offset

            try:
                resp = await self._http.post(
                    f"{self.config.qdrant_url}/collections/{self.config.collection}/points/scroll",
                    json=scroll_body,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"Qdrant scroll error during rebuild: {e}")
                break

            result = data.get("result", {})
            points = result.get("points", [])

            if not points:
                break

            for point in points:
                vec = point.get("vector")
                pid = point.get("id")
                if vec and pid:
                    all_vectors.append(vec)
                    all_ids.append(str(pid))

            offset = result.get("next_page_offset")
            if offset is None:
                break

        if not all_vectors:
            logger.warning("No vectors found in Qdrant for rebuild")
            return 0

        vectors_matrix = np.array(all_vectors, dtype=np.float32)
        count = self.hasher.rebuild_from_vectors(vectors_matrix, all_ids)

        # Persist immediately
        hash_path = os.path.join(self.config.data_dir, "hash_index.pkl")
        self.hasher.save(hash_path)

        logger.info(f"Hash index rebuilt: {count} documents")
        return count
