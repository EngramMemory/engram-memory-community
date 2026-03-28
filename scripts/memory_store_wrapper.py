#!/usr/bin/env python3
"""
Memory Store Wrapper - Proper argument parsing for OpenClaw integration
"""

import sys
import json
import argparse
from pathlib import Path

# Add the parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import the existing memory store functionality  
from memory_store import MemoryStore

def main():
    """Main entry point with proper argument parsing"""
    parser = argparse.ArgumentParser(description="Store text in memory with semantic embedding")
    parser.add_argument("--text", required=True, help="Text to store")
    parser.add_argument("--category", default="other", help="Memory category")
    parser.add_argument("--importance", type=float, default=0.5, help="Importance score (0-1)")
    parser.add_argument("--metadata", help="JSON metadata")
    
    args = parser.parse_args()
    
    try:
        # Parse metadata if provided
        metadata = {}
        if args.metadata:
            metadata = json.loads(args.metadata)
        
        # Create memory store instance and store the text
        store = MemoryStore()
        
        memory_id = store.store_memory(
            text=args.text,
            category=args.category,
            importance=args.importance,
            metadata=metadata
        )
        
        print(json.dumps({
            "success": True,
            "memory_id": memory_id,
            "text": args.text,
            "category": args.category,
            "importance": args.importance
        }, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        sys.exit(1)

if __name__ == "__main__":
    main()