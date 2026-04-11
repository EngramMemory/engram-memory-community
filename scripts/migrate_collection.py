#!/usr/bin/env python3
"""
Migrate agent-memory (flat schema) → agent-memory-v2 (hybrid schema).

Steps:
  1. Scroll all 23 points from agent-memory (flat vectors + payloads)
  2. Generate BM25 sparse vectors from text content
  3. Insert into agent-memory-v2 with named vectors (dense + bm25)
  4. Update server config default to agent-memory-v2

Does NOT delete agent-memory — kept as backup.
"""

import hashlib
import math
import re
import sys
import time
from collections import Counter

import httpx

QDRANT_URL = "http://localhost:6333"
SRC_COLLECTION = "agent-memory"
DST_COLLECTION = "agent-memory-v2"

# ── BM25 sparse vector (copied from recall_engine.py) ──────────────

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


def text_to_sparse_vector(text: str, boost_specifics: bool = False):
    tokens = re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", text.lower())
    tokens = [t for t in tokens if t not in _STOPWORDS and len(t) > 1]
    if not tokens:
        return {"indices": [], "values": []}
    tf = Counter(tokens)
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]} {tokens[i+1]}"
        tf[bigram] = tf.get(bigram, 0) + 1
    indices, values = [], []
    for token, count in tf.items():
        idx = int(hashlib.md5(token.encode()).hexdigest()[:8], 16) & 0x3FFFFFFF
        weight = 1.0 + math.log(count) if count > 1 else 1.0
        if boost_specifics and re.match(r"^[0-9]", token):
            weight *= 1.5
        indices.append(idx)
        values.append(round(weight, 4))
    return {"indices": indices, "values": values}


def main():
    client = httpx.Client(timeout=30.0)

    # 1. Verify both collections exist
    for col in [SRC_COLLECTION, DST_COLLECTION]:
        r = client.get(f"{QDRANT_URL}/collections/{col}")
        if r.status_code != 200:
            print(f"ERROR: Collection '{col}' not found")
            sys.exit(1)

    # 2. Get existing point count in dst
    r = client.get(f"{QDRANT_URL}/collections/{DST_COLLECTION}")
    dst_count = r.json()["result"]["points_count"]
    print(f"Destination '{DST_COLLECTION}' has {dst_count} existing points")

    # 3. Scroll all points from source
    all_points = []
    offset = None
    while True:
        body = {"limit": 100, "with_payload": True, "with_vector": True}
        if offset is not None:
            body["offset"] = offset
        r = client.post(f"{QDRANT_URL}/collections/{SRC_COLLECTION}/points/scroll", json=body)
        r.raise_for_status()
        result = r.json()["result"]
        points = result.get("points", [])
        if not points:
            break
        all_points.extend(points)
        offset = result.get("next_page_offset")
        if offset is None:
            break

    print(f"Read {len(all_points)} points from '{SRC_COLLECTION}'")

    if not all_points:
        print("Nothing to migrate.")
        return

    # 4. Transform and insert into destination
    batch = []
    for pt in all_points:
        pid = pt["id"]
        payload = pt.get("payload", {})
        flat_vector = pt.get("vector", [])

        # Get text for BM25
        text = payload.get("content", payload.get("text", ""))
        sparse = text_to_sparse_vector(text, boost_specifics=True)

        # Ensure payload has both text and content fields
        if "content" not in payload and "text" in payload:
            payload["content"] = payload["text"]

        # Add created_at if missing
        if "created_at" not in payload:
            ts = payload.get("timestamp")
            if ts:
                # Convert ISO timestamp to epoch
                from datetime import datetime
                try:
                    payload["created_at"] = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except Exception:
                    payload["created_at"] = time.time()
            else:
                payload["created_at"] = time.time()

        # Add access_count if missing
        if "access_count" not in payload:
            payload["access_count"] = 0

        batch.append({
            "id": pid,
            "vector": {
                "dense": flat_vector,
                "bm25": sparse,
            },
            "payload": payload,
        })

    # Upsert in batches of 50
    for i in range(0, len(batch), 50):
        chunk = batch[i:i+50]
        r = client.put(
            f"{QDRANT_URL}/collections/{DST_COLLECTION}/points",
            json={"points": chunk},
        )
        r.raise_for_status()
        print(f"  Upserted {len(chunk)} points (batch {i//50 + 1})")

    # 5. Verify
    r = client.get(f"{QDRANT_URL}/collections/{DST_COLLECTION}")
    final_count = r.json()["result"]["points_count"]
    print(f"\nMigration complete. '{DST_COLLECTION}' now has {final_count} points.")
    print(f"'{SRC_COLLECTION}' preserved as backup ({len(all_points)} points).")


if __name__ == "__main__":
    main()
