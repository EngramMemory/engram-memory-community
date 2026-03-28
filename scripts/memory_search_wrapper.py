#!/usr/bin/env python3
"""
Memory Search Wrapper - Proper argument parsing for OpenClaw integration
"""

import sys
import json
import argparse
from pathlib import Path

# Add the parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the existing memory search functionality
from memory_search import MemorySearch

def main():
    """Main entry point with proper argument parsing"""
    parser = argparse.ArgumentParser(description="Search memories using semantic similarity")
    parser.add_argument("--query", required=True, help="Search query text")
    parser.add_argument("--limit", type=int, default=10, help="Maximum results to return")
    parser.add_argument("--min-score", type=float, default=0.0, help="Minimum similarity score")
    parser.add_argument("--category", help="Filter by category")
    
    args = parser.parse_args()
    
    try:
        searcher = MemorySearch()
        results = searcher.search(
            query=args.query,
            limit=args.limit,
            min_score=args.min_score,
            category=args.category
        )
        
        print(json.dumps({
            "query": args.query,
            "results": results,
            "count": len(results)
        }, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(1)

if __name__ == "__main__":
    main()