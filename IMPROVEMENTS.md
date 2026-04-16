# Engram Memory — Improvement Roadmap

Based on Competitive Benchmark 2026 (Engram vs mem0 vs supermemory)

## Current Standing

| Metric | Engram | supermemory | mem0 |
|---|---|---|---|
| Store throughput | **13.3 ops/s** | 0.7 | 2.0 |
| R@1 | 0.72 | **0.88** | 0.40 |
| R@3 | **0.92** | **0.92** | 0.48 |
| R@5 | **0.96** | **0.96** | 0.56 |
| R@10 | **1.00** | 0.96 | 0.64 |
| MRR | 0.83 | **0.91** | 0.46 |
| Search p95 | 519 ms | 852 ms | 392 ms |
| LLM cost/query | **$0** | ~$0.003 | ~$0.005 |

**Engram wins**: throughput (18x SM), deep recall (R@10 = 1.0), zero LLM cost
**Engram loses**: R@1 precision (0.72 vs 0.88), classification (60%)

---

## Priority 1: Client-Side LLM Reranking (closes R@1 gap)

### The Architecture

Supermemory pays for server-side LLM reranking on every query. We can get the same result for free by leveraging the user's model that's *already running*.

**How it works:**

1. Agent (Claude/GPT/etc) calls `memory_search(query)` via MCP
2. Engram returns top-10 candidates with scores (as today)
3. MCP response includes a `rerank_hint` field — a structured prompt fragment
4. The calling model naturally reranks by reading the results (it already does this)
5. On next `memory_store` or `memory_recall`, the agent can pass back `rerank_feedback` with the IDs it actually used
6. Engram ingests this signal to boost those memories in the hot tier

**What this gives us:**
- R@1 improvement without any LLM cost to Engram
- User's model does the work it would do anyway (reading search results)
- Feedback loop makes future searches better
- Data stays local — the reranking happens on the user's machine
- Cloud tier gets the signal too (for users who opt in)

### Implementation

**Phase A — Structured results for natural reranking:**
- Return results with clear `relevance_context` field per result
- Include `query_intent` classification in response metadata
- The calling model reads these and naturally picks the best match

**Phase B — Feedback ingestion:**
- Add `rerank_feedback` parameter to `memory_recall` and `memory_store`
- Accept: `{query_id, selected_ids: [...], rejected_ids: [...]}`
- Boost selected IDs in hot tier (increase ACT-R activation)
- Penalize rejected IDs for similar future queries
- Store in Kuzu graph as `PREFERRED_OVER` edges

**Phase C — Cloud learning (opt-in):**
- Aggregate reranking signals across users (anonymized)
- Train lightweight cross-encoder on accumulated preferences
- Ship as model update (not data — preserves sovereignty)

### Files to modify
- `src/recall/recall_engine.py` — search() return format, hot-tier boost logic
- `src/recall/models.py` — add RerankerFeedback model
- `mcp/server.py` — add rerank_feedback parameter to tools
- `docker/mcp/entrypoint.py` — REST endpoint changes

---

## Priority 2: Classification Improvements (60% → 85%+)

### Current failures
| Text | Expected | Got | Missing pattern |
|---|---|---|---|
| "launches on March 15th" | fact | other | temporal: "launch, scheduled, occur" |
| "every first Friday" | fact | entity | "company" matched entity before fact |
| "migration window Sunday 2-4 AM" | fact | other | "scheduled, recurring, window" |
| "Chose Figma over Sketch" | decision | other | "chose" (past tense) |

### Fix: Expand patterns + add priority ordering
```python
_CATEGORY_PATTERNS = {
    "preference": re.compile(r"\b(prefer|like|always|never|want|love|hate|enjoy|favor|rather|choose to|tend to|usually|my favorite)\b", re.I),
    "decision": re.compile(r"\b(decided|chose|chosen|selected|will use|going with|switched to|moved to|picking|opted for|committed to|approved|rejected|went with)\b", re.I),
    "fact": re.compile(r"\b(completed|version|status|count|runs|running|deployed|migrated|installed|updated|currently|uses|located|configured|set to|costs|takes|measures|port|scheduled|launches?|occurs?|every \w+day|recurring|window|at \d+:\d+)\b", re.I),
    "entity": re.compile(r"\b(company|hive|person|project|service|app|platform|organization|department|manager|lead|owner|maintainer|vendor|client)\b", re.I),
}
```

**Also add**: pattern priority so "decision" beats "entity" when both match (e.g., "chose" + "company" should be decision).

---

## Priority 3: False Positive Reduction (neg score 0.5 → <0.35)

### Problem
Negative queries (completely unrelated) return scores up to 0.5, which is above the `min_recall_score` threshold of 0.35. This means the system returns confident-looking results for irrelevant queries.

### Fix options
1. **Dynamic threshold**: Use calibrated negative query scores as floor
2. **Score normalization**: Normalize scores relative to query-corpus distribution
3. **Confidence interval**: Return a confidence band, not just a point score
4. **Hard fix**: Lower `min_recall_score` to 0.25 (quick, may hurt recall)

---

## Priority 4: Hash Tier Utilization (10% → 30%+)

### Problem
Only 10% of queries use the O(1) hash lookup. Most fall through to 600-800ms vector search.

### Root cause
Multi-head hasher with 4 heads x 12-bit hashing is too sparse. Hash collisions are rare, so few queries find candidates.

### Fix
- Increase to 6 heads or 14-16 bit hashing
- Lower hash similarity threshold for candidate generation
- Use hash tier as pre-filter for vector search (reduce search space)

---

## Priority 5: Vector Collision ("Platform hive" problem)

### Problem
5 of 7 R@1 misses return "The Platform hive (5 engineers) owns Kubernetes infrastructure and CI/CD" as top result. This single memory is a false-positive magnet because it contains: "hive", "engineers", "infrastructure", "CI/CD" — generic high-IDF terms.

### Root cause
BM25 sparse vectors over-weight common infrastructure terms. RRF fusion doesn't penalize memories that match too many queries (low specificity).

### Fix options
1. **IDF penalty**: Penalize memories that appear in top-k for >30% of queries
2. **Specificity score**: Weight memories by inverse of how many queries they match
3. **Query expansion**: Before search, classify query intent and boost category-matched results
4. **Negative feedback**: After reranking (Priority 1), auto-penalize repeated false positives

---

## Priority 6: Hot Tier Pre-warming

### Observation
Engram gets faster at scale (878ms → 356ms) but only because of cache warming during the test. First-query experience is always slow.

### Fix
- On startup, pre-compute hot-tier entries for recently accessed memories
- Use Kuzu graph to predict likely query patterns from stored relationships
- Background job that refreshes hot-tier embeddings every N minutes

---

## Competitive Positioning

### vs supermemory
- **We win**: throughput (18x), deep recall (R@10), zero cost, data sovereignty
- **They win**: R@1 precision (LLM reranking), time-to-value (hosted)
- **Close with**: Priority 1 (client-side reranking) closes the R@1 gap at zero cost
- **Messaging**: "Same accuracy, 18x faster, your data stays local, no per-query fees"

### vs mem0
- **We win**: everything except raw search latency
- **They lose**: LLM extraction drops memories (R@10 = 0.64), DNS reliability issues
- **Messaging**: "We store what you tell us. They store what their LLM thinks is important."

### vs Zep
- **Published**: ~8 ops/s store, ~180ms search p50, R@5 = 0.82
- **We win**: throughput (13.3 vs 8), recall (R@5 = 0.96 vs 0.82)
- **They win**: search latency (180ms vs 480ms — likely server-side, no embedding overhead)
