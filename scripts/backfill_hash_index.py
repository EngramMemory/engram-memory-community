#!/usr/bin/env python3
"""
Backfill the multi-head hash index from all vectors in agent-memory-v2.

Uses the recall engine's rebuild_hash_index() method, which:
  1. Scrolls all points from Qdrant
  2. Builds LSH index from dense vectors
  3. Persists to data_dir/hash_index.pkl
"""

import asyncio
import os
import sys

# Add src/recall to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "recall"))

from recall_engine import EngramRecallEngine
from models import EngramConfig

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "mcp", ".engram")


async def main():
    config = EngramConfig(
        qdrant_url="http://localhost:6333",
        embedding_url="http://localhost:11435",
        collection="agent-memory-v2",
        data_dir=os.path.abspath(DATA_DIR),
        auto_persist=False,
        graph_enabled=False,
        consolidation_enabled=False,
    )
    config.ensure_data_dir()

    engine = EngramRecallEngine(config)
    await engine.warmup()

    count = await engine.rebuild_hash_index()
    print(f"Hash index rebuilt: {count} documents indexed")
    print(f"Saved to: {os.path.join(config.data_dir, 'hash_index.pkl')}")

    await engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
