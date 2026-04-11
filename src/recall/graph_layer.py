"""
Engram Memory — Knowledge Graph Layer
=======================================
Embedded Kuzu graph for entity tracking, spreading activation,
and co-retrieval patterns. No server, no network — runs locally.

Community Edition: 500 entities, 1-hop traversal, 10 connections per query.
Cloud Edition: Unlimited entities, multi-hop, LLM-powered NER.
"""

import logging
import os
import re
import time
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import kuzu

logger = logging.getLogger("engram.graph")

# Community Edition limits
COMMUNITY_MAX_ENTITIES = 500
COMMUNITY_MAX_HOPS = 1
COMMUNITY_MAX_CONNECTIONS_PER_QUERY = 10


# ─── Entity Extraction (regex, no LLM) ──────────────────────────────

def extract_entities(text: str) -> List[Tuple[str, str]]:
    """Extract entities from text using regex patterns.

    Returns list of (entity_name, entity_type) tuples.
    Community: regex-based (covers ~70% of entities).
    Cloud: LLM-powered NER for full coverage.
    """
    entities = []
    seen = set()

    def add(name: str, etype: str):
        key = name.lower().strip()
        if key and key not in seen and len(key) > 1:
            seen.add(key)
            entities.append((name.strip(), etype))

    # Version strings: PostgreSQL 16.2, v1.2.3, Python 3.12
    for m in re.finditer(r"(?:v\.?)?(\d+\.\d+(?:\.\d+)?)", text):
        # Check if preceded by a product name
        start = max(0, m.start() - 30)
        prefix = text[start:m.start()].strip()
        words = prefix.split()
        if words:
            product = words[-1]
            if product[0].isupper():
                add(f"{product} {m.group()}", "version")
            else:
                add(m.group(), "version")
        else:
            add(m.group(), "version")

    # ALL_CAPS acronyms (3+ chars): AWS, RDS, API, CI/CD
    for m in re.finditer(r"\b([A-Z][A-Z/]{2,})\b", text):
        add(m.group(1), "acronym")

    # Capitalized multi-word phrases: "GitHub Actions", "AWS RDS", "Let's Encrypt"
    for m in re.finditer(r"([A-Z][a-zA-Z']+(?:\s+[A-Z][a-zA-Z']+)+)", text):
        phrase = m.group(1)
        # Skip phrases starting with common words
        if not phrase.split()[0].lower() in {"the", "this", "that", "chose", "decided", "agreed"}:
            add(phrase, "noun_phrase")

    # CamelCase words: DigitalOcean, PostgreSQL, GitHub
    for m in re.finditer(r"\b([A-Z][a-z]+[A-Z][a-zA-Z]*)\b", text):
        add(m.group(1), "proper_noun")

    # Single capitalized words that look like proper nouns
    for m in re.finditer(r"(?:^|\s)([A-Z][a-z]{2,})\b", text):
        word = m.group(1)
        # Skip common English words that happen to be capitalized
        if word.lower() not in {"the", "this", "that", "with", "from", "they",
                                 "have", "been", "will", "would", "could", "should",
                                 "community", "edition", "cloud", "upgrade", "max",
                                 "user", "team", "project", "vendor", "server",
                                 "memory", "database", "production", "staging",
                                 "chose", "decided", "agreed", "selected", "deployed",
                                 "stored", "created", "updated", "removed", "added"}:
            add(word, "proper_noun")

    # Quoted strings
    for m in re.finditer(r'"([^"]{2,50})"', text):
        add(m.group(1), "quoted")

    # @mentions
    for m in re.finditer(r"@(\w{2,})", text):
        add(m.group(1), "mention")

    # Port numbers in context
    for m in re.finditer(r"port\s+(\d{2,5})", text, re.IGNORECASE):
        add(f"port {m.group(1)}", "port")

    # IP addresses
    for m in re.finditer(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", text):
        add(m.group(1), "ip_address")

    return entities


# ─── Graph Layer ─────────────────────────────────────────────────────

class EngramGraphLayer:
    """Embedded Kuzu knowledge graph for memory relationships."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        # Kuzu creates the directory itself — ensure parent exists
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db = kuzu.Database(db_path)
        self.conn = kuzu.Connection(self.db)
        self._entity_count = 0

    def ensure_schema(self):
        """Create tables if they don't exist. Idempotent."""
        stmts = [
            # Node tables
            "CREATE NODE TABLE IF NOT EXISTS Memory(id STRING, content STRING, category STRING, created_at DOUBLE, PRIMARY KEY(id))",
            "CREATE NODE TABLE IF NOT EXISTS Entity(name STRING, entity_type STRING, PRIMARY KEY(name))",
            "CREATE NODE TABLE IF NOT EXISTS Concept(id STRING, label STRING, created_at DOUBLE, PRIMARY KEY(id))",
            # Edge tables
            "CREATE REL TABLE IF NOT EXISTS MENTIONS(FROM Memory TO Entity)",
            "CREATE REL TABLE IF NOT EXISTS RELATED_TO(FROM Memory TO Memory, weight DOUBLE)",
            "CREATE REL TABLE IF NOT EXISTS CO_RETRIEVED(FROM Memory TO Memory, count INT64, last_time DOUBLE)",
            "CREATE REL TABLE IF NOT EXISTS PREFERRED_OVER(FROM Memory TO Memory, query_hash STRING, count INT64, last_time DOUBLE)",
        ]
        for stmt in stmts:
            try:
                self.conn.execute(stmt)
            except Exception as e:
                logger.debug(f"Schema stmt skipped: {e}")

        # Cache entity count
        try:
            result = self.conn.execute("MATCH (e:Entity) RETURN count(e) AS c")
            while result.has_next():
                self._entity_count = result.get_next()[0]
        except Exception:
            self._entity_count = 0

    def upsert_memory_node(self, doc_id: str, content: str, category: str, created_at: float):
        """Insert or update a Memory node."""
        try:
            self.conn.execute(
                "MERGE (m:Memory {id: $id}) SET m.content = $content, m.category = $category, m.created_at = $created_at",
                {"id": doc_id, "content": content[:500], "category": category, "created_at": created_at},
            )
        except Exception as e:
            logger.debug(f"Memory node upsert failed: {e}")

    def add_entity_mentions(self, doc_id: str, entities: List[Tuple[str, str]]):
        """Add Entity nodes and MENTIONS edges from a memory."""
        if self._entity_count >= COMMUNITY_MAX_ENTITIES:
            logger.warning(
                f"Community Edition supports max {COMMUNITY_MAX_ENTITIES} entity nodes. "
                f"Upgrade to Engram Cloud for unlimited entities with LLM-powered NER."
            )
            return

        for name, etype in entities:
            if self._entity_count >= COMMUNITY_MAX_ENTITIES:
                break
            try:
                self.conn.execute(
                    "MERGE (e:Entity {name: $name}) SET e.entity_type = $etype",
                    {"name": name.lower()[:200], "etype": etype},
                )
                self._entity_count += 1
                self.conn.execute(
                    "MATCH (m:Memory {id: $mid}), (e:Entity {name: $ename}) "
                    "MERGE (m)-[:MENTIONS]->(e)",
                    {"mid": doc_id, "ename": name.lower()[:200]},
                )
            except Exception as e:
                logger.debug(f"Entity mention failed: {e}")

    def add_co_retrieval(self, doc_ids: List[str]):
        """Record that these memories were co-retrieved in the same search."""
        if len(doc_ids) < 2:
            return
        now = time.time()
        for a, b in combinations(doc_ids[:10], 2):  # Cap pairs to avoid O(n²) explosion
            try:
                # Try to increment existing edge
                result = self.conn.execute(
                    "MATCH (a:Memory {id: $a})-[r:CO_RETRIEVED]->(b:Memory {id: $b}) "
                    "SET r.count = r.count + 1, r.last_time = $now "
                    "RETURN r.count",
                    {"a": a, "b": b, "now": now},
                )
                if not result.has_next():
                    # Create new edge
                    self.conn.execute(
                        "MATCH (a:Memory {id: $a}), (b:Memory {id: $b}) "
                        "CREATE (a)-[:CO_RETRIEVED {count: 1, last_time: $now}]->(b)",
                        {"a": a, "b": b, "now": now},
                    )
            except Exception as e:
                logger.debug(f"Co-retrieval tracking failed: {e}")

    def get_related_memory_ids(
        self, doc_id: str, max_hops: int = 1, limit: int = 10
    ) -> List[str]:
        """Get memory IDs related to the given memory via graph traversal."""
        if max_hops > COMMUNITY_MAX_HOPS:
            logger.warning(
                f"Community Edition supports max {COMMUNITY_MAX_HOPS}-hop traversal. "
                f"Upgrade to Engram Cloud for deep multi-hop spreading activation."
            )
        max_hops = min(max_hops, COMMUNITY_MAX_HOPS)
        limit = min(limit, COMMUNITY_MAX_CONNECTIONS_PER_QUERY)

        related = set()

        # 1. Shared entities: memories that mention the same entities
        try:
            result = self.conn.execute(
                "MATCH (m:Memory {id: $id})-[:MENTIONS]->(e:Entity)<-[:MENTIONS]-(other:Memory) "
                "WHERE other.id <> $id "
                "RETURN DISTINCT other.id LIMIT $limit",
                {"id": doc_id, "limit": limit},
            )
            while result.has_next():
                related.add(result.get_next()[0])
        except Exception as e:
            logger.debug(f"Entity traversal failed: {e}")

        # 2. Co-retrieved memories
        try:
            result = self.conn.execute(
                "MATCH (m:Memory {id: $id})-[r:CO_RETRIEVED]-(other:Memory) "
                "WHERE other.id <> $id "
                "RETURN other.id ORDER BY r.count DESC LIMIT $limit",
                {"id": doc_id, "limit": limit},
            )
            while result.has_next():
                related.add(result.get_next()[0])
        except Exception as e:
            logger.debug(f"Co-retrieval traversal failed: {e}")

        # 3. Explicit RELATED_TO edges
        try:
            result = self.conn.execute(
                "MATCH (m:Memory {id: $id})-[r:RELATED_TO]-(other:Memory) "
                "WHERE other.id <> $id "
                "RETURN other.id ORDER BY r.weight DESC LIMIT $limit",
                {"id": doc_id, "limit": limit},
            )
            while result.has_next():
                related.add(result.get_next()[0])
        except Exception as e:
            logger.debug(f"Related traversal failed: {e}")

        return list(related)[:limit]

    def get_memories_for_entity(self, entity_name: str, limit: int = 20) -> List[str]:
        """Get all memory IDs that mention a specific entity."""
        try:
            result = self.conn.execute(
                "MATCH (m:Memory)-[:MENTIONS]->(e:Entity {name: $name}) "
                "RETURN m.id LIMIT $limit",
                {"name": entity_name.lower(), "limit": limit},
            )
            ids = []
            while result.has_next():
                ids.append(result.get_next()[0])
            return ids
        except Exception as e:
            logger.debug(f"Entity lookup failed: {e}")
            return []

    def remove_memory(self, doc_id: str):
        """Remove a memory node and all its edges."""
        try:
            self.conn.execute(
                "MATCH (m:Memory {id: $id}) DETACH DELETE m",
                {"id": doc_id},
            )
        except Exception as e:
            logger.debug(f"Memory removal failed: {e}")

    def add_preference(self, selected_id: str, rejected_id: str, query_hash: str):
        """Record that selected_id was preferred over rejected_id for a query."""
        now = time.time()
        try:
            result = self.conn.execute(
                "MATCH (a:Memory {id: $sel})-[r:PREFERRED_OVER]->(b:Memory {id: $rej}) "
                "WHERE r.query_hash = $qh "
                "SET r.count = r.count + 1, r.last_time = $now "
                "RETURN r.count",
                {"sel": selected_id, "rej": rejected_id, "qh": query_hash, "now": now},
            )
            if not result.has_next():
                self.conn.execute(
                    "MATCH (a:Memory {id: $sel}), (b:Memory {id: $rej}) "
                    "CREATE (a)-[:PREFERRED_OVER {query_hash: $qh, count: 1, last_time: $now}]->(b)",
                    {"sel": selected_id, "rej": rejected_id, "qh": query_hash, "now": now},
                )
        except Exception as e:
            logger.debug(f"Preference recording failed: {e}")

    def get_preference_boost(self, doc_id: str, limit: int = 5) -> int:
        """Get how many times this memory has been preferred over others."""
        try:
            result = self.conn.execute(
                "MATCH (m:Memory {id: $id})-[r:PREFERRED_OVER]->() RETURN sum(r.count) AS total",
                {"id": doc_id},
            )
            if result.has_next():
                val = result.get_next()[0]
                return int(val) if val else 0
        except Exception:
            pass
        return 0

    def get_stats(self) -> Dict:
        """Get node and edge counts."""
        stats = {}
        for label, query in [
            ("memory_nodes", "MATCH (m:Memory) RETURN count(m)"),
            ("entity_nodes", "MATCH (e:Entity) RETURN count(e)"),
            ("concept_nodes", "MATCH (c:Concept) RETURN count(c)"),
            ("mentions_edges", "MATCH ()-[r:MENTIONS]->() RETURN count(r)"),
            ("related_edges", "MATCH ()-[r:RELATED_TO]->() RETURN count(r)"),
            ("co_retrieved_edges", "MATCH ()-[r:CO_RETRIEVED]->() RETURN count(r)"),
        ]:
            try:
                result = self.conn.execute(query)
                if result.has_next():
                    stats[label] = result.get_next()[0]
            except Exception:
                stats[label] = 0
        return stats

    def close(self):
        """Close the database connection."""
        try:
            self.conn.close()
        except Exception:
            pass
