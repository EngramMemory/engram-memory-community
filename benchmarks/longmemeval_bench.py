#!/usr/bin/env python3
"""
Engram x LongMemEval Benchmark
================================

Evaluates Engram's retrieval against the LongMemEval benchmark.

For each of the 500 questions:
1. Create a fresh Qdrant collection
2. Ingest all haystack sessions (embed via FastEmbed HTTP, store in Qdrant)
3. Query with question text
4. Score retrieval against ground-truth answer_session_ids

Outputs:
- Recall@k and NDCG@k at session and turn level
- Per-question-type breakdown

Requirements:
    - Qdrant running on localhost:6333
    - FastEmbed HTTP running on localhost:11435

Usage:
    python benchmarks/longmemeval_bench.py [--limit N] [--granularity session|turn]
"""

import json
import argparse
import math
import os
import sys
import uuid
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import httpx

# =============================================================================
# CONFIG
# =============================================================================

FASTEMBED_URL = os.environ.get("FASTEMBED_URL", "http://localhost:11435")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "engram_longmemeval_test"
DATASET_URL = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json"
DATA_DIR = Path(__file__).parent / "data"
DATA_FILE = DATA_DIR / "longmemeval_s_cleaned.json"
EMBED_BATCH_SIZE = 16  # FastEmbed batch size (small to avoid timeouts on long docs)

# =============================================================================
# DATASET DOWNLOAD
# =============================================================================


def ensure_dataset():
    """Download dataset if not cached locally."""
    if DATA_FILE.exists():
        print(f"  Dataset cached: {DATA_FILE}")
        return DATA_FILE

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading dataset from HuggingFace...")
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        resp = client.get(DATASET_URL)
        resp.raise_for_status()
        DATA_FILE.write_bytes(resp.content)
    size_mb = DATA_FILE.stat().st_size / (1024 * 1024)
    print(f"  Downloaded: {DATA_FILE} ({size_mb:.1f} MB)")
    return DATA_FILE


# =============================================================================
# METRICS
# =============================================================================


def dcg(relevances, k):
    """Discounted Cumulative Gain."""
    score = 0.0
    for i, rel in enumerate(relevances[:k]):
        score += rel / math.log2(i + 2)
    return score


def ndcg(rankings, correct_ids, corpus_ids, k):
    """Normalized DCG."""
    relevances = [1.0 if corpus_ids[idx] in correct_ids else 0.0 for idx in rankings[:k]]
    ideal = sorted(relevances, reverse=True)
    idcg = dcg(ideal, k)
    if idcg == 0:
        return 0.0
    return dcg(relevances, k) / idcg


def evaluate_retrieval(rankings, correct_ids, corpus_ids, k):
    """
    Evaluate retrieval at rank k.
    Returns (recall_any, recall_all, ndcg_score).
    """
    top_k_ids = set(corpus_ids[idx] for idx in rankings[:k])
    recall_any = float(any(cid in top_k_ids for cid in correct_ids))
    recall_all = float(all(cid in top_k_ids for cid in correct_ids))
    ndcg_score = ndcg(rankings, correct_ids, corpus_ids, k)
    return recall_any, recall_all, ndcg_score


def session_id_from_corpus_id(corpus_id):
    """Extract session ID from a corpus ID (handles both session and turn granularity)."""
    if "_turn_" in corpus_id:
        return corpus_id.rsplit("_turn_", 1)[0]
    return corpus_id


# =============================================================================
# EMBEDDING + QDRANT HELPERS
# =============================================================================

_http = None


def get_http():
    global _http
    if _http is None:
        _http = httpx.Client(timeout=300)
    return _http


def embed_texts(texts, embed_type="passage"):
    """Embed texts via FastEmbed HTTP service.

    Args:
        texts: list of strings to embed
        embed_type: "passage" for storage, "query" for search
    Returns:
        list of embedding vectors
    """
    client = get_http()
    all_embeddings = []
    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        resp = client.post(
            f"{FASTEMBED_URL}/embeddings",
            json={"texts": batch, "type": embed_type},
        )
        resp.raise_for_status()
        data = resp.json()
        # Handle both {"embeddings": [...]} and direct list response
        if isinstance(data, dict) and "embeddings" in data:
            all_embeddings.extend(data["embeddings"])
        elif isinstance(data, list):
            all_embeddings.extend(data)
        else:
            raise ValueError(f"Unexpected FastEmbed response format: {type(data)}")
    return all_embeddings


def get_embedding_dim():
    """Probe FastEmbed to discover embedding dimensionality."""
    vecs = embed_texts(["test"], embed_type="passage")
    return len(vecs[0])


def reset_collection(dim):
    """Delete and recreate the test collection with given vector dimension."""
    client = get_http()
    # Delete if exists (ignore errors)
    try:
        client.delete(f"{QDRANT_URL}/collections/{COLLECTION_NAME}")
    except Exception:
        pass
    # Create fresh
    resp = client.put(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}",
        json={
            "vectors": {"size": dim, "distance": "Cosine"},
        },
    )
    resp.raise_for_status()


def upsert_points(ids, vectors, payloads):
    """Batch upsert points into Qdrant."""
    client = get_http()
    points = []
    for pid, vec, payload in zip(ids, vectors, payloads):
        points.append({"id": pid, "vector": vec, "payload": payload})

    # Qdrant batch limit ~100 points per call for reliability
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        resp = client.put(
            f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points",
            json={"points": batch},
        )
        resp.raise_for_status()


def search_points(query_vector, limit=50):
    """Search Qdrant for nearest neighbors."""
    client = get_http()
    resp = client.post(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/query",
        json={
            "query": query_vector,
            "limit": limit,
            "with_payload": True,
        },
    )
    resp.raise_for_status()
    return resp.json()["result"]["points"]


# =============================================================================
# RETRIEVER
# =============================================================================


def build_corpus_and_retrieve(entry, granularity="session", n_results=50, embed_dim=None):
    """
    Build corpus from haystack sessions, embed, store in Qdrant, query.

    Returns:
        rankings: list of indices into corpus (descending relevance)
        corpus: list of document strings
        corpus_ids: list of document IDs (session or turn level)
        corpus_timestamps: list of timestamps
    """
    corpus = []
    corpus_ids = []
    corpus_timestamps = []

    sessions = entry["haystack_sessions"]
    session_ids = entry["haystack_session_ids"]
    dates = entry["haystack_dates"]

    for sess_idx, (session, sess_id, date) in enumerate(zip(sessions, session_ids, dates)):
        if granularity == "session":
            user_turns = [t["content"] for t in session if t["role"] == "user"]
            if user_turns:
                doc = "\n".join(user_turns)
                corpus.append(doc)
                corpus_ids.append(sess_id)
                corpus_timestamps.append(date)
        else:
            turn_num = 0
            for turn in session:
                if turn["role"] == "user":
                    corpus.append(turn["content"])
                    corpus_ids.append(f"{sess_id}_turn_{turn_num}")
                    corpus_timestamps.append(date)
                    turn_num += 1

    if not corpus:
        return [], corpus, corpus_ids, corpus_timestamps

    # Reset collection
    reset_collection(embed_dim)

    # Embed all corpus documents (passage type)
    embeddings = embed_texts(corpus, embed_type="passage")

    # Generate integer point IDs for Qdrant
    point_ids = list(range(len(corpus)))
    payloads = [
        {"corpus_idx": i, "corpus_id": cid, "timestamp": ts}
        for i, (cid, ts) in enumerate(zip(corpus_ids, corpus_timestamps))
    ]

    # Upsert into Qdrant
    upsert_points(point_ids, embeddings, payloads)

    # Embed query (query type)
    query_vec = embed_texts([entry["question"]], embed_type="query")[0]

    # Search
    results = search_points(query_vec, limit=min(n_results, len(corpus)))

    # Map results back to corpus indices
    ranked_indices = [pt["payload"]["corpus_idx"] for pt in results]

    # Fill in any missing indices
    seen = set(ranked_indices)
    for i in range(len(corpus)):
        if i not in seen:
            ranked_indices.append(i)

    return ranked_indices, corpus, corpus_ids, corpus_timestamps


# =============================================================================
# BENCHMARK RUNNER
# =============================================================================


def run_benchmark(data_file, granularity="session", limit=0):
    """Run the full LongMemEval benchmark."""
    with open(data_file) as f:
        data = json.load(f)

    if limit > 0:
        data = data[:limit]

    # Probe embedding dimension
    print("  Probing FastEmbed for embedding dimension...")
    embed_dim = get_embedding_dim()
    print(f"  Embedding dim: {embed_dim}")

    print(f"\n{'=' * 60}")
    print("  Engram x LongMemEval Benchmark")
    print(f"{'=' * 60}")
    print(f"  Data:        {Path(data_file).name}")
    print(f"  Questions:   {len(data)}")
    print(f"  Granularity: {granularity}")
    print(f"  FastEmbed:   {FASTEMBED_URL}")
    print(f"  Qdrant:      {QDRANT_URL}")
    print(f"  Collection:  {COLLECTION_NAME}")
    print(f"{'─' * 60}\n")

    # Metrics
    ks = [1, 3, 5, 10]
    metrics_session = {f"recall_any@{k}": [] for k in ks}
    metrics_session.update({f"recall_all@{k}": [] for k in ks})
    metrics_session.update({f"ndcg_any@{k}": [] for k in ks})

    metrics_turn = {f"recall_any@{k}": [] for k in ks}
    metrics_turn.update({f"recall_all@{k}": [] for k in ks})
    metrics_turn.update({f"ndcg_any@{k}": [] for k in ks})

    per_type = defaultdict(lambda: defaultdict(list))
    start_time = datetime.now()

    for i, entry in enumerate(data):
        qid = entry["question_id"]
        qtype = entry["question_type"]
        question = entry["question"]
        answer_sids = set(entry["answer_session_ids"])

        # Run retrieval
        rankings, corpus, corpus_ids, corpus_timestamps = build_corpus_and_retrieve(
            entry, granularity=granularity, embed_dim=embed_dim,
        )

        if not rankings:
            print(f"  [{i + 1:4}/{len(data)}] {qid[:30]:30} SKIP (empty corpus)")
            continue

        # Session-level IDs
        session_level_ids = [session_id_from_corpus_id(cid) for cid in corpus_ids]
        session_correct = answer_sids

        # Turn-level correct IDs
        turn_correct = set()
        for cid in corpus_ids:
            sid = session_id_from_corpus_id(cid)
            if sid in answer_sids:
                turn_correct.add(cid)

        entry_metrics = {"session": {}, "turn": {}}

        for k in ks:
            # Session-level
            ra, rl, nd = evaluate_retrieval(rankings, session_correct, session_level_ids, k)
            metrics_session[f"recall_any@{k}"].append(ra)
            metrics_session[f"recall_all@{k}"].append(rl)
            metrics_session[f"ndcg_any@{k}"].append(nd)
            entry_metrics["session"][f"recall_any@{k}"] = ra

            # Turn-level
            ra_t, rl_t, nd_t = evaluate_retrieval(rankings, turn_correct, corpus_ids, k)
            metrics_turn[f"recall_any@{k}"].append(ra_t)
            metrics_turn[f"recall_all@{k}"].append(rl_t)
            metrics_turn[f"ndcg_any@{k}"].append(nd_t)

        # Per-type tracking
        per_type[qtype]["recall_any@5"].append(metrics_session["recall_any@5"][-1])
        per_type[qtype]["recall_any@10"].append(metrics_session["recall_any@10"][-1])
        per_type[qtype]["ndcg_any@10"].append(metrics_session["ndcg_any@10"][-1])

        # Progress line
        r5 = metrics_session["recall_any@5"][-1]
        r10 = metrics_session["recall_any@10"][-1]
        status = "HIT" if r5 > 0 else "miss"
        print(f"  [{i + 1:4}/{len(data)}] {qid[:30]:30} R@5={r5:.0f} R@10={r10:.0f}  {status}")

    elapsed = (datetime.now() - start_time).total_seconds()

    # Print results
    print(f"\n{'=' * 60}")
    print(f"  RESULTS — Engram ({granularity} granularity)")
    print(f"{'=' * 60}")
    if data:
        print(f"  Time: {elapsed:.1f}s ({elapsed / len(data):.2f}s per question)\n")

    print("  SESSION-LEVEL METRICS:")
    for k in ks:
        vals = metrics_session[f"recall_any@{k}"]
        if vals:
            ra = sum(vals) / len(vals)
            nd = sum(metrics_session[f"ndcg_any@{k}"]) / len(metrics_session[f"ndcg_any@{k}"])
            print(f"    Recall@{k:2}: {ra:.3f}    NDCG@{k:2}: {nd:.3f}")

    print("\n  TURN-LEVEL METRICS:")
    for k in ks:
        vals = metrics_turn[f"recall_any@{k}"]
        if vals:
            ra = sum(vals) / len(vals)
            nd = sum(metrics_turn[f"ndcg_any@{k}"]) / len(metrics_turn[f"ndcg_any@{k}"])
            print(f"    Recall@{k:2}: {ra:.3f}    NDCG@{k:2}: {nd:.3f}")

    print(f"\n  PER-TYPE BREAKDOWN (session recall_any@10):")
    for qtype, vals in sorted(per_type.items()):
        r10 = sum(vals["recall_any@10"]) / len(vals["recall_any@10"])
        n = len(vals["recall_any@10"])
        print(f"    {qtype:40} R@10={r10:.3f}  (n={n})")

    print(f"\n{'=' * 60}\n")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Engram x LongMemEval Benchmark")
    parser.add_argument(
        "--granularity",
        choices=["session", "turn"],
        default="session",
        help="Retrieval granularity (default: session)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit to N questions (0 = all)")
    args = parser.parse_args()

    # Preflight: check services
    client = httpx.Client(timeout=5)
    try:
        client.get(f"{QDRANT_URL}/collections")
    except Exception:
        print(f"ERROR: Qdrant not reachable at {QDRANT_URL}")
        sys.exit(1)
    try:
        client.get(f"{FASTEMBED_URL}/health")
    except Exception:
        # Some FastEmbed servers don't have /health, try embeddings
        try:
            client.post(f"{FASTEMBED_URL}/embeddings", json={"texts": ["ping"], "type": "query"})
        except Exception:
            print(f"ERROR: FastEmbed not reachable at {FASTEMBED_URL}")
            sys.exit(1)
    client.close()

    data_path = ensure_dataset()
    run_benchmark(str(data_path), granularity=args.granularity, limit=args.limit)
