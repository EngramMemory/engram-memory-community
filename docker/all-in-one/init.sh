#!/bin/sh
# Engram all-in-one init: prepare data dirs and bootstrap the Qdrant
# collection before the MCP server starts.
#
# This is the same bootstrap that scripts/setup.sh runs externally for
# the 3-container deployment, just done inside the container so the
# all-in-one image is self-contained.
set -e

DATA="${DATA_DIR_ROOT:-/data}"

mkdir -p "$DATA/qdrant"
mkdir -p "$DATA/engram"

# Symlink Qdrant storage to persistent volume so vector data survives restarts
if [ ! -L /qdrant/storage ] && [ ! -d /qdrant/storage ]; then
    mkdir -p /qdrant
    ln -s "$DATA/qdrant" /qdrant/storage
fi

echo "Engram all-in-one: data dir=$DATA"

# Background: wait for Qdrant + FastEmbed, then create the collection.
# Runs in background so init returns quickly and the longrun services can
# start. The MCP server's own dependencies make it wait for Qdrant + FastEmbed.
(
    # Wait for Qdrant
    for i in $(seq 1 60); do
        if curl -sf http://localhost:6333/healthz >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    # Wait for FastEmbed
    for i in $(seq 1 120); do
        if curl -sf http://localhost:11435/health >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    # Create the agent-memory collection if it does not exist yet.
    # Same schema as scripts/setup.sh: 768-dim dense (cosine) + BM25 sparse
    # for hybrid search, with optimization hints tuned for single-machine.
    if ! curl -sf http://localhost:6333/collections/agent-memory >/dev/null 2>&1; then
        curl -sf -X PUT http://localhost:6333/collections/agent-memory \
            -H "Content-Type: application/json" \
            -d '{
                "vectors": {
                    "dense": {
                        "size": 768,
                        "distance": "Cosine"
                    }
                },
                "sparse_vectors": {
                    "bm25": {}
                },
                "optimizers_config": {
                    "default_segment_number": 2
                },
                "replication_factor": 1
            }' >/dev/null 2>&1 \
            && echo "Engram all-in-one: collection 'agent-memory' bootstrapped" \
            || echo "Engram all-in-one: collection bootstrap failed (will retry on next start)"
    else
        echo "Engram all-in-one: collection 'agent-memory' already exists"
    fi
) &

echo "Engram all-in-one: init complete"
