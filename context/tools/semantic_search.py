#!/usr/bin/env python3
"""
Engram Semantic Search Tool

Provides semantic search capabilities for context files using embeddings.
Integrates with Engram's memory system for enhanced search.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import sqlite3
import hashlib

import click
from dataclasses import dataclass, asdict

# Try to import optional dependencies
try:
    import httpx
    import numpy as np
    HAS_SEMANTIC = True
except ImportError:
    HAS_SEMANTIC = False

logger = logging.getLogger(__name__)


@dataclass
class SemanticSearchResult:
    """Semantic search result with embedding similarity."""
    file_path: str
    content: str
    similarity_score: float
    metadata: Dict[str, Any]
    snippet: str


class SemanticSearchEngine:
    """Semantic search engine for context files."""
    
    def __init__(self, project_root: str = None):
        """Initialize semantic search engine."""
        if project_root:
            self.project_root = Path(project_root).resolve()
        else:
            self.project_root = self._find_project_root()
        
        self.context_dir = self.project_root / ".context"
        self.semantic_index_file = self.context_dir / "semantic_index.db"
        
        # Check for embedding service
        self.embedding_url = os.getenv('EMBEDDING_URL', 'http://localhost:11435')
        self.embedding_model = os.getenv('EMBEDDING_MODEL', 'nomic-ai/nomic-embed-text-v1.5')
        
        if not HAS_SEMANTIC:
            print("⚠️  Semantic search dependencies not installed.")
            print("   Run: pip install httpx numpy")
            sys.exit(1)
    
    def _find_project_root(self) -> Path:
        """Find project root by looking for common markers."""
        current = Path.cwd()
        markers = ['.git', '.context', 'package.json', 'pyproject.toml']
        
        while current != current.parent:
            for marker in markers:
                if (current / marker).exists():
                    return current
            current = current.parent
        
        return Path.cwd()
    
    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text using local embedding service."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.embedding_url}/embeddings",
                    json={"texts": [text]},
                    timeout=30
                )

                if response.status_code == 200:
                    result = response.json()
                    return result["embeddings"][0]
                else:
                    print(f"Embedding service error: {response.status_code}")
                    return None
                    
        except Exception as e:
            print(f"Failed to get embedding: {e}")
            return None
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            import numpy as np
            
            a = np.array(vec1)
            b = np.array(vec2)
            
            dot_product = np.dot(a, b)
            norm_a = np.linalg.norm(a)
            norm_b = np.linalg.norm(b)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            return dot_product / (norm_a * norm_b)
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0
    
    async def build_semantic_index(self) -> Dict[str, Any]:
        """Build semantic index using embeddings."""
        print("🧠 Building semantic search index...")
        
        if not self.context_dir.exists():
            print("❌ No context directory found. Run 'engram context init' first.")
            return {"success": False, "error": "No context directory"}
        
        # Initialize semantic index database
        conn = sqlite3.connect(self.semantic_index_file)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_files (
                path TEXT PRIMARY KEY,
                content_hash TEXT,
                content TEXT,
                embedding BLOB,
                metadata TEXT,
                indexed_at TEXT
            )
        """)
        
        # Process all context files
        context_files = list(self.context_dir.glob("*.md"))
        indexed_count = 0
        
        for file_path in context_files:
            if file_path.name.startswith('.') or file_path.name == 'semantic_index.db':
                continue
            
            print(f"  📄 Processing {file_path.name}...")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Calculate content hash
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            # Check if file needs reindexing
            cursor = conn.execute(
                "SELECT content_hash FROM semantic_files WHERE path = ?",
                (str(file_path.relative_to(self.context_dir)),)
            )
            existing = cursor.fetchone()
            
            if existing and existing[0] == content_hash:
                print(f"    ⏭️  Skipping (unchanged)")
                continue
            
            # Extract metadata from frontmatter
            metadata = {}
            clean_content = content
            if content.startswith('---'):
                try:
                    frontmatter_end = content.find('---', 3)
                    if frontmatter_end > 0:
                        import yaml
                        frontmatter = content[3:frontmatter_end].strip()
                        metadata = yaml.safe_load(frontmatter)
                        clean_content = content[frontmatter_end + 3:].strip()
                except:
                    pass
            
            # Get embedding for content
            embedding = await self._get_embedding(clean_content)
            if not embedding:
                print(f"    ❌ Failed to get embedding for {file_path.name}")
                continue
            
            # Store in database
            embedding_blob = json.dumps(embedding).encode('utf-8')
            conn.execute("""
                INSERT OR REPLACE INTO semantic_files
                (path, content_hash, content, embedding, metadata, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(file_path.relative_to(self.context_dir)),
                content_hash,
                clean_content,
                embedding_blob,
                json.dumps(metadata),
                datetime.now().isoformat()
            ))
            
            indexed_count += 1
            print(f"    ✅ Indexed with {len(embedding)}-dim embedding")
        
        conn.commit()
        conn.close()
        
        print(f"✅ Semantic index complete: {indexed_count} files processed")
        return {
            "success": True,
            "files_processed": indexed_count,
            "total_files": len(context_files),
            "index_updated": datetime.now().isoformat()
        }
    
    async def search_semantic(self, query: str, limit: int = 5, threshold: float = 0.3) -> List[SemanticSearchResult]:
        """Search context files using semantic similarity."""
        if not self.semantic_index_file.exists():
            print("⚠️  No semantic index found. Run 'engram context semantic index' first.")
            return []
        
        print(f"🔍 Semantic search: {query}")
        
        # Get query embedding
        query_embedding = await self._get_embedding(query)
        if not query_embedding:
            print("❌ Failed to get query embedding")
            return []
        
        # Search index
        conn = sqlite3.connect(self.semantic_index_file)
        cursor = conn.execute("""
            SELECT path, content, embedding, metadata
            FROM semantic_files
        """)
        
        results = []
        for row in cursor.fetchall():
            path, content, embedding_blob, metadata_json = row
            
            try:
                # Deserialize embedding
                embedding = json.loads(embedding_blob.decode('utf-8'))
                
                # Calculate similarity
                similarity = self._cosine_similarity(query_embedding, embedding)
                
                if similarity >= threshold:
                    # Extract metadata
                    try:
                        metadata = json.loads(metadata_json)
                    except:
                        metadata = {}
                    
                    # Create snippet
                    snippet = content[:300] + "..." if len(content) > 300 else content
                    
                    results.append(SemanticSearchResult(
                        file_path=path,
                        content=content,
                        similarity_score=similarity,
                        metadata=metadata,
                        snippet=snippet
                    ))
                    
            except Exception as e:
                logger.error(f"Error processing result for {path}: {e}")
                continue
        
        conn.close()
        
        # Sort by similarity and limit results
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:limit]
    
    def get_semantic_status(self) -> Dict[str, Any]:
        """Get semantic search system status."""
        status = {
            "semantic_available": HAS_SEMANTIC,
            "embedding_service": self.embedding_url,
            "embedding_model": self.embedding_model,
            "index_exists": self.semantic_index_file.exists(),
            "index_stats": None
        }
        
        if self.semantic_index_file.exists():
            try:
                conn = sqlite3.connect(self.semantic_index_file)
                cursor = conn.execute("SELECT COUNT(*) FROM semantic_files")
                file_count = cursor.fetchone()[0]
                
                cursor = conn.execute("""
                    SELECT indexed_at FROM semantic_files 
                    ORDER BY indexed_at DESC LIMIT 1
                """)
                last_updated = cursor.fetchone()
                
                conn.close()
                
                status["index_stats"] = {
                    "file_count": file_count,
                    "last_updated": last_updated[0] if last_updated else None
                }
            except Exception as e:
                status["index_error"] = str(e)
        
        return status
    
    async def test_embedding_service(self) -> Dict[str, Any]:
        """Test connection to embedding service."""
        try:
            test_embedding = await self._get_embedding("test query")
            
            if test_embedding:
                return {
                    "available": True,
                    "embedding_dimension": len(test_embedding),
                    "model": self.embedding_model,
                    "url": self.embedding_url
                }
            else:
                return {
                    "available": False,
                    "error": "No embedding returned",
                    "url": self.embedding_url
                }
                
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "url": self.embedding_url
            }


@click.group()
@click.pass_context
def cli(ctx):
    """Engram Semantic Search"""
    ctx.ensure_object(dict)


@cli.command()
@click.option('--project', default='.', help='Project root directory')
@click.pass_context
def index(ctx, project):
    """Build semantic search index."""
    engine = SemanticSearchEngine(project)
    result = asyncio.run(engine.build_semantic_index())
    
    if result.get('success'):
        print(f"📊 Semantic indexing complete:")
        print(f"  • Files processed: {result['files_processed']}")
        print(f"  • Total files: {result['total_files']}")
        print(f"  • Updated: {result['index_updated']}")
    else:
        print(f"❌ Indexing failed: {result.get('error', 'Unknown error')}")


@cli.command()
@click.argument('query')
@click.option('--limit', default=5, help='Maximum number of results')
@click.option('--threshold', default=0.3, help='Minimum similarity threshold')
@click.option('--project', default='.', help='Project root directory')
@click.pass_context
def find(ctx, query, limit, threshold, project):
    """Search context files semantically."""
    engine = SemanticSearchEngine(project)
    results = asyncio.run(engine.search_semantic(query, limit, threshold))
    
    if not results:
        print(f"🔍 No semantic results found for: {query}")
        print(f"   (threshold: {threshold})")
        return
    
    print(f"🧠 Found {len(results)} semantic results for: {query}\n")
    
    for i, result in enumerate(results, 1):
        print(f"{i}. 📄 {result.file_path} (similarity: {result.similarity_score:.3f})")
        print(f"   {result.snippet}")
        if result.metadata.get('description'):
            print(f"   💡 {result.metadata['description']}")
        print()


@cli.command()
@click.option('--project', default='.', help='Project root directory')
@click.pass_context
def status(ctx, project):
    """Show semantic search status."""
    engine = SemanticSearchEngine(project)
    status = engine.get_semantic_status()
    
    print("🧠 Semantic Search Status:")
    print(f"  Dependencies: {'✅ Available' if status['semantic_available'] else '❌ Missing'}")
    print(f"  Service: {status['embedding_service']}")
    print(f"  Model: {status['embedding_model']}")
    print(f"  Index: {'✅ Built' if status['index_exists'] else '❌ Not built'}")
    
    if status.get('index_stats'):
        stats = status['index_stats']
        print(f"  Files: {stats['file_count']}")
        if stats['last_updated']:
            print(f"  Updated: {stats['last_updated']}")
    
    if status.get('index_error'):
        print(f"  Error: {status['index_error']}")


@cli.command()
@click.option('--project', default='.', help='Project root directory')
@click.pass_context
def test_service(ctx, project):
    """Test embedding service connection."""
    engine = SemanticSearchEngine(project)
    result = asyncio.run(engine.test_embedding_service())
    
    print("🧠 Embedding Service Test:")
    
    if result['available']:
        print("✅ Service available")
        print(f"  Embedding dimension: {result['embedding_dimension']}")
        print(f"  Model: {result['model']}")
        print(f"  URL: {result['url']}")
    else:
        print("❌ Service unavailable")
        print(f"  Error: {result['error']}")
        print(f"  URL: {result['url']}")
        print("\n💡 To setup embedding service:")
        print("   1. Ensure Engram is running: bash scripts/setup.sh")
        print("   2. Check FastEmbed service: curl http://localhost:11435/health")


if __name__ == '__main__':
    cli()