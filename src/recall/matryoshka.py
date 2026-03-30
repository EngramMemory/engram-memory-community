"""
Engram Memory — Matryoshka Vector Utilities
============================================
Variable-dimension vector slicing for tiered retrieval.

Supports Matryoshka Representation Learning (MRL) models where
semantic meaning is front-loaded into early dimensions. The first
64 dims carry ~90% of the signal; full 768 dims carry 100%.

Community Edition: Fixed slices at 64 (hash), 256 (filter), 768 (rank).
Cloud Edition: Arbitrary dimension selection + fine-tuned Engram MRL model.
"""

import numpy as np
from typing import Union, List, Tuple

# Community Edition fixed slice points
SLICE_FAST = 64      # For Multi-Head Hashing (Tier 2)
SLICE_MEDIUM = 256   # For candidate pre-filtering
SLICE_FULL = 768     # For final re-ranking (Tier 3)

SUPPORTED_DIMS = (64, 128, 256, 512, 768)


def normalize(vec: np.ndarray) -> np.ndarray:
    """L2-normalize a vector. Returns zero vector if norm is 0."""
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def slice_vector(
    vec: Union[np.ndarray, List[float]],
    dim: int,
    do_normalize: bool = True
) -> np.ndarray:
    """
    Slice a vector to the first `dim` dimensions and optionally normalize.

    In MRL-trained models, truncated vectors must be re-normalized to
    maintain valid cosine similarity scores.

    Args:
        vec: Full embedding vector (768-dim for nomic-embed-text-v1.5)
        dim: Target dimensionality (must be <= len(vec))
        do_normalize: Whether to L2-normalize after slicing (recommended)

    Returns:
        np.ndarray of shape (dim,)
    """
    v = np.asarray(vec, dtype=np.float32)
    if dim > len(v):
        raise ValueError(
            f"Cannot slice to {dim} dims — vector only has {len(v)} dims"
        )
    sliced = v[:dim]
    return normalize(sliced) if do_normalize else sliced


def get_fast_slice(vec: Union[np.ndarray, List[float]]) -> np.ndarray:
    """First 64 dims — used for Multi-Head Hashing (O(1) lookup)."""
    return slice_vector(vec, SLICE_FAST)


def get_medium_slice(vec: Union[np.ndarray, List[float]]) -> np.ndarray:
    """First 256 dims — used for candidate pre-filtering."""
    return slice_vector(vec, SLICE_MEDIUM)


def get_full_vector(vec: Union[np.ndarray, List[float]]) -> np.ndarray:
    """Full 768 dims — used for final cosine re-ranking."""
    return slice_vector(vec, SLICE_FULL)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Cosine similarity between two vectors.
    If both are already L2-normalized, this is just a dot product.
    """
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def batch_cosine_similarity(
    query: np.ndarray,
    candidates: np.ndarray
) -> np.ndarray:
    """
    Cosine similarity between a query vector and a matrix of candidates.

    Args:
        query: (dim,) query vector
        candidates: (N, dim) matrix of candidate vectors

    Returns:
        (N,) array of similarity scores
    """
    query = np.asarray(query, dtype=np.float32)
    candidates = np.asarray(candidates, dtype=np.float32)

    query_norm = np.linalg.norm(query)
    if query_norm == 0:
        return np.zeros(candidates.shape[0])

    q = query / query_norm
    norms = np.linalg.norm(candidates, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)  # avoid div by zero
    c = candidates / norms

    return c @ q


def validate_vector(
    vec: Union[np.ndarray, List[float]],
    expected_dim: int = SLICE_FULL
) -> Tuple[bool, str]:
    """
    Validate a vector for storage in Engram.

    Returns:
        (is_valid, message)
    """
    v = np.asarray(vec, dtype=np.float32)

    if v.ndim != 1:
        return False, f"Expected 1D vector, got {v.ndim}D"

    if len(v) < SLICE_FAST:
        return False, f"Vector too short ({len(v)} dims). Minimum is {SLICE_FAST}."

    if len(v) != expected_dim:
        return False, (
            f"Vector has {len(v)} dims, expected {expected_dim}. "
            f"This may indicate a model mismatch."
        )

    if np.any(np.isnan(v)):
        return False, "Vector contains NaN values"

    if np.any(np.isinf(v)):
        return False, "Vector contains Inf values"

    norm = np.linalg.norm(v)
    if norm == 0:
        return False, "Zero vector — embedding likely failed"

    return True, "OK"
