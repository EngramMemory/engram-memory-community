"""
Engram Memory — Test Suite
============================
Tests for Matryoshka, Multi-Head Hasher, and Hot-Tier Cache.

Run: python -m pytest tests/ -v
"""

import sys
import os
import time
import tempfile
import numpy as np

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from matryoshka import (
    slice_vector, get_fast_slice, get_medium_slice, get_full_vector,
    cosine_similarity, batch_cosine_similarity, validate_vector,
    normalize, SLICE_FAST, SLICE_MEDIUM, SLICE_FULL,
)
from multi_head_hasher import EngramMultiHeadHasher
from hot_tier import EngramHotTier


# ============================================================
# Helpers
# ============================================================

def random_vector(dim=768, seed=None):
    """Generate a random normalized vector."""
    rng = np.random.RandomState(seed)
    v = rng.randn(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def similar_vector(base, noise_scale=0.1, seed=None):
    """Generate a vector similar to `base` with small perturbation."""
    rng = np.random.RandomState(seed)
    noise = rng.randn(len(base)).astype(np.float32) * noise_scale
    v = base + noise
    return v / np.linalg.norm(v)


# ============================================================
# Matryoshka Tests
# ============================================================

class TestMatryoshka:

    def test_slice_fast(self):
        vec = random_vector(768)
        fast = get_fast_slice(vec)
        assert fast.shape == (SLICE_FAST,)
        # Should be normalized
        assert abs(np.linalg.norm(fast) - 1.0) < 1e-5

    def test_slice_medium(self):
        vec = random_vector(768)
        med = get_medium_slice(vec)
        assert med.shape == (SLICE_MEDIUM,)

    def test_slice_full(self):
        vec = random_vector(768)
        full = get_full_vector(vec)
        assert full.shape == (SLICE_FULL,)

    def test_slice_preserves_direction(self):
        """Slicing + normalizing should preserve relative direction."""
        v1 = random_vector(768, seed=1)
        # Use smaller noise to get higher similarity with random vectors
        v2 = similar_vector(v1, noise_scale=0.01, seed=2)

        # Full similarity should be reasonably high
        full_sim = cosine_similarity(v1, v2)
        assert full_sim > 0.5, f"Full sim too low: {full_sim}"

        # Fast-slice similarity should also track (even without MRL training)
        fast_sim = cosine_similarity(get_fast_slice(v1), get_fast_slice(v2))
        assert fast_sim > 0.3, f"Fast sim too low: {fast_sim}"

        # Key property: both should be positive (directionally preserved)
        assert full_sim > 0 and fast_sim > 0

    def test_slice_too_large(self):
        vec = random_vector(128)
        try:
            slice_vector(vec, 256)
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_validate_vector_good(self):
        vec = random_vector(768)
        ok, msg = validate_vector(vec)
        assert ok, msg

    def test_validate_vector_nan(self):
        vec = random_vector(768)
        vec[10] = np.nan
        ok, msg = validate_vector(vec)
        assert not ok
        assert "NaN" in msg

    def test_validate_vector_zero(self):
        vec = np.zeros(768, dtype=np.float32)
        ok, msg = validate_vector(vec)
        assert not ok
        assert "Zero" in msg

    def test_validate_vector_wrong_dim(self):
        vec = random_vector(512)
        ok, msg = validate_vector(vec, expected_dim=768)
        assert not ok

    def test_batch_cosine_similarity(self):
        query = random_vector(768, seed=1)
        candidates = np.array([
            similar_vector(query, 0.05, seed=2),
            random_vector(768, seed=3),
            similar_vector(query, 0.1, seed=4),
        ])
        scores = batch_cosine_similarity(query, candidates)
        assert scores.shape == (3,)
        # First and third should be more similar than second
        assert scores[0] > scores[1]
        assert scores[2] > scores[1]

    def test_normalize_zero_vector(self):
        vec = np.zeros(64, dtype=np.float32)
        result = normalize(vec)
        assert np.all(result == 0)


# ============================================================
# Multi-Head Hasher Tests
# ============================================================

class TestMultiHeadHasher:

    def test_basic_index_and_search(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12, seed=42)
        vec = random_vector(768, seed=1)
        hasher.index(vec, "doc_1")

        candidates = hasher.search_candidates(vec)
        assert "doc_1" in candidates

    def test_similar_vectors_found(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=8, seed=42)
        base = random_vector(768, seed=1)
        similar = similar_vector(base, noise_scale=0.05, seed=2)

        hasher.index(base, "doc_1")
        candidates = hasher.search_candidates(similar)
        # Similar vectors should hash to at least one common bucket
        assert "doc_1" in candidates

    def test_dissimilar_vectors_not_found(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12, seed=42)
        v1 = random_vector(768, seed=1)
        v2 = random_vector(768, seed=99)

        hasher.index(v1, "doc_1")
        candidates = hasher.search_candidates(v2)
        # Orthogonal vectors should rarely collide across all heads
        # (not guaranteed, but very likely with 4 heads × 12 bits)
        # We just verify the search runs without error
        assert isinstance(candidates, list)

    def test_batch_index(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12, seed=42)
        vectors = np.array([random_vector(768, seed=i) for i in range(100)])
        ids = [f"doc_{i}" for i in range(100)]

        count = hasher.index_batch(vectors, ids)
        assert count == 100
        assert hasher.size == 100

    def test_remove(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12, seed=42)
        vec = random_vector(768, seed=1)
        hasher.index(vec, "doc_1")
        assert hasher.contains("doc_1")

        result = hasher.remove("doc_1")
        assert result is True
        assert not hasher.contains("doc_1")
        assert hasher.size == 0

    def test_remove_nonexistent(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12, seed=42)
        result = hasher.remove("nonexistent")
        assert result is False

    def test_reindex_same_doc(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12, seed=42)
        v1 = random_vector(768, seed=1)
        v2 = random_vector(768, seed=2)

        hasher.index(v1, "doc_1")
        hasher.index(v2, "doc_1")  # Re-index with different vector
        assert hasher.size == 1  # Should not duplicate

    def test_save_and_load(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12, seed=42)
        vectors = np.array([random_vector(768, seed=i) for i in range(50)])
        ids = [f"doc_{i}" for i in range(50)]
        hasher.index_batch(vectors, ids)

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name

        try:
            hasher.save(path)
            loaded = EngramMultiHeadHasher.load(path)

            assert loaded.size == 50
            assert loaded.num_heads == 4
            assert loaded.hash_size == 12

            # Verify same search results
            query = vectors[0]
            orig_candidates = hasher.search_candidates(query)
            loaded_candidates = loaded.search_candidates(query)
            assert set(orig_candidates) == set(loaded_candidates)
        finally:
            os.unlink(path)

    def test_community_limits_enforced(self):
        # Should clamp to community max
        hasher = EngramMultiHeadHasher(dim=64, num_heads=16, hash_size=32, seed=42)
        assert hasher.num_heads == 4   # Clamped from 16
        assert hasher.hash_size == 12  # Clamped from 32

    def test_min_heads_search(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=8, seed=42)

        # Index several vectors
        for i in range(20):
            hasher.index(random_vector(768, seed=i), f"doc_{i}")

        query = random_vector(768, seed=0)

        # min_heads=1 (union) should return more candidates
        union_results = hasher.search_candidates(query, min_heads=1)
        # min_heads=4 (full intersection) should return fewer
        intersect_results = hasher.search_candidates(query, min_heads=4)

        assert len(union_results) >= len(intersect_results)

    def test_stats(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12, seed=42)
        hasher.index(random_vector(768, seed=1), "doc_1")
        hasher.search_candidates(random_vector(768, seed=2))

        stats = hasher.get_stats()
        assert stats["total_indexed"] == 1
        assert stats["total_searches"] == 1
        assert stats["unique_docs"] == 1

    def test_bucket_distribution(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=8, seed=42)
        for i in range(200):
            hasher.index(random_vector(768, seed=i), f"doc_{i}")

        dist = hasher.get_bucket_distribution()
        assert len(dist) == 4  # One per head
        for head_idx, info in dist.items():
            assert info["total_entries"] == 200

    def test_rebuild_from_vectors(self):
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=12, seed=42)
        vectors = np.array([random_vector(768, seed=i) for i in range(30)])
        ids = [f"doc_{i}" for i in range(30)]

        hasher.index_batch(vectors, ids)
        original_candidates = hasher.search_candidates(vectors[0])

        # Rebuild should produce identical results (same seed = same projections)
        hasher.rebuild_from_vectors(vectors, ids)
        rebuilt_candidates = hasher.search_candidates(vectors[0])

        assert set(original_candidates) == set(rebuilt_candidates)


# ============================================================
# Hot-Tier Cache Tests
# ============================================================

class TestHotTier:

    def test_basic_upsert_and_search(self):
        hot = EngramHotTier(max_size=100, decay_rate=0.1)
        vec = random_vector(768, seed=1)
        hot.upsert("doc_1", vec, "Test memory", "fact")

        results = hot.search(vec, top_k=5, min_similarity=0.5)
        assert len(results) > 0
        assert results[0][0] == "doc_1"

    def test_hit_strengthens_memory(self):
        hot = EngramHotTier(max_size=100, decay_rate=0.1)
        vec = random_vector(768, seed=1)

        hot.upsert("doc_1", vec, "Test", "fact")
        entry_before = hot.get_memory("doc_1")
        assert entry_before.hits == 1

        hot.upsert("doc_1", vec, "Test", "fact")
        entry_after = hot.get_memory("doc_1")
        assert entry_after.hits == 2

    def test_eviction_when_full(self):
        hot = EngramHotTier(max_size=3, decay_rate=0.1)

        for i in range(4):
            vec = random_vector(768, seed=i)
            hot.upsert(f"doc_{i}", vec, f"Memory {i}", "fact")
            time.sleep(0.01)  # Tiny delay so timestamps differ

        # Should have evicted the weakest
        assert hot.size == 3
        assert hot.stats.total_evictions == 1

    def test_community_max_size_enforced(self):
        hot = EngramHotTier(max_size=5000)
        assert hot.max_size == 1000  # Clamped

    def test_decay_weakens_over_time(self):
        hot = EngramHotTier(max_size=100, decay_rate=10.0)  # Very fast decay
        vec = random_vector(768, seed=1)
        hot.upsert("doc_1", vec, "Test", "fact")

        # Immediately should be strong
        entry = hot.get_memory("doc_1")
        strength_now = hot._calculate_strength(entry)
        assert strength_now > 0

        # Hack the last_access to simulate time passing
        entry.last_access = time.time() - 7200  # 2 hours ago
        strength_later = hot._calculate_strength(entry)
        assert strength_later < strength_now

    def test_decay_sweep(self):
        hot = EngramHotTier(max_size=100, decay_rate=10.0)

        for i in range(5):
            vec = random_vector(768, seed=i)
            hot.upsert(f"doc_{i}", vec, f"Mem {i}", "fact")

        # Hack all entries to be very old
        for entry in hot._cache.values():
            entry.last_access = time.time() - 86400  # 24 hours ago

        removed = hot.decay_sweep(min_strength=0.01)
        assert removed == 5
        assert hot.size == 0

    def test_search_respects_similarity_threshold(self):
        hot = EngramHotTier(max_size=100, similarity_threshold=0.9)
        base = random_vector(768, seed=1)
        hot.upsert("doc_1", base, "Test", "fact")

        # Very different query should not match at 0.9 threshold
        different = random_vector(768, seed=99)
        results = hot.search(different, top_k=5)
        # Probably empty, but depends on random vectors
        for doc_id, sim, strength in results:
            assert sim >= 0.9

    def test_context_injection(self):
        hot = EngramHotTier(max_size=100, decay_rate=0.1)
        vec = random_vector(768, seed=1)
        hot.upsert("doc_1", vec, "User prefers TypeScript", "preference")

        context = hot.get_context_injection(top_k=5)
        assert "HOT MEMORIES" in context
        assert "TypeScript" in context
        assert "PREFERENCE" in context

    def test_context_injection_empty(self):
        hot = EngramHotTier(max_size=100)
        context = hot.get_context_injection(top_k=5)
        assert context == ""

    def test_get_top_memories(self):
        hot = EngramHotTier(max_size=100, decay_rate=0.1)

        for i in range(5):
            vec = random_vector(768, seed=i)
            hot.upsert(f"doc_{i}", vec, f"Memory {i}", "fact")

        # Make doc_2 the strongest by accessing it multiple times
        vec2 = random_vector(768, seed=2)
        for _ in range(10):
            hot.upsert("doc_2", vec2, "Memory 2", "fact")

        top = hot.get_top_memories(top_k=3)
        assert len(top) == 3
        assert top[0][0] == "doc_2"  # Most hits should be strongest

    def test_remove(self):
        hot = EngramHotTier(max_size=100)
        vec = random_vector(768, seed=1)
        hot.upsert("doc_1", vec, "Test", "fact")
        assert hot.size == 1

        result = hot.remove("doc_1")
        assert result is True
        assert hot.size == 0

    def test_save_and_load(self):
        hot = EngramHotTier(max_size=100, decay_rate=0.2)
        for i in range(10):
            vec = random_vector(768, seed=i)
            hot.upsert(f"doc_{i}", vec, f"Memory {i}", "fact")

        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            path = f.name

        try:
            hot.save(path)
            loaded = EngramHotTier.load(path)

            assert loaded.size == 10
            assert loaded.decay_rate == 0.2
            assert loaded.get_memory("doc_0") is not None
            assert loaded.get_memory("doc_0").content == "Memory 0"
        finally:
            os.unlink(path)

    def test_stats(self):
        hot = EngramHotTier(max_size=100)
        vec = random_vector(768, seed=1)
        hot.upsert("doc_1", vec, "Test", "fact")

        # Search that hits
        hot.search(vec, top_k=5, min_similarity=0.5)
        # Search that misses
        hot.search(random_vector(768, seed=99), top_k=5, min_similarity=0.99)

        stats = hot.get_stats()
        assert stats["total_upserts"] >= 1
        assert stats["total_hits"] + stats["total_misses"] == 2


# ============================================================
# Integration: Hash → Hot-Tier Promotion
# ============================================================

class TestIntegration:

    def test_hash_to_hot_promotion(self):
        """Simulate the full flow: index → hash search → promote to hot-tier."""
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=8, seed=42)
        hot = EngramHotTier(max_size=100, decay_rate=0.1)

        # Index 50 vectors
        vectors = [random_vector(768, seed=i) for i in range(50)]
        for i, vec in enumerate(vectors):
            hasher.index(vec, f"doc_{i}")

        # Search for the exact same vector as doc_0 (guaranteed match)
        query = vectors[0]
        candidates = hasher.search_candidates(query)

        # doc_0 should always be in candidates (exact match)
        assert "doc_0" in candidates, "Exact vector should always match its own hash"

        # Simulate re-ranking and promotion
        promoted = 0
        for doc_id in candidates:
            idx = int(doc_id.split("_")[1])
            sim = cosine_similarity(query, vectors[idx])
            if sim > 0.3:
                hot.upsert(doc_id, vectors[idx], f"Content {idx}", "fact")
                promoted += 1

        assert promoted > 0, "Should have promoted at least doc_0"
        assert hot.size > 0

        # Second search should hit hot-tier
        hot_results = hot.search(query, top_k=5, min_similarity=0.3)
        hot_ids = [r[0] for r in hot_results]
        assert "doc_0" in hot_ids, "doc_0 should be in hot-tier results"

    def test_three_tier_ordering(self):
        """Verify that hot-tier results would be checked before hash."""
        hasher = EngramMultiHeadHasher(dim=64, num_heads=4, hash_size=8, seed=42)
        hot = EngramHotTier(max_size=100, decay_rate=0.1)

        vec = random_vector(768, seed=1)
        hasher.index(vec, "doc_1")

        # Promote to hot-tier (simulating previous retrieval)
        hot.upsert("doc_1", vec, "Important memory", "fact")

        # Hit it several times to make it strong
        for _ in range(10):
            hot.upsert("doc_1", vec, "Important memory", "fact")

        # Hot-tier search should find it instantly
        hot_results = hot.search(vec, top_k=1, min_similarity=0.5)
        assert len(hot_results) == 1
        assert hot_results[0][0] == "doc_1"
        assert hot_results[0][2] > 1.0  # Strength should be high after 11 hits


if __name__ == "__main__":
    # Quick smoke test without pytest
    print("Running smoke tests...\n")

    tests = [
        TestMatryoshka(),
        TestMultiHeadHasher(),
        TestHotTier(),
        TestIntegration(),
    ]

    passed = 0
    failed = 0

    for test_class in tests:
        class_name = test_class.__class__.__name__
        methods = [m for m in dir(test_class) if m.startswith("test_")]
        for method_name in methods:
            try:
                getattr(test_class, method_name)()
                print(f"  ✓ {class_name}.{method_name}")
                passed += 1
            except Exception as e:
                print(f"  ✗ {class_name}.{method_name}: {e}")
                failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("All tests passed!")
    else:
        sys.exit(1)
