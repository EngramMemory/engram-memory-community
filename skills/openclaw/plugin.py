#!/usr/bin/env python3
"""
Engram OpenClaw Plugin

This script provides the OpenClaw plugin interface for Engram memory operations.
It bridges OpenClaw's tool calling system with our FastEmbed + Qdrant backend.
"""

import sys
import json
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, List

def get_script_dir():
    """Get the directory containing this script"""
    return Path(__file__).parent

def run_memory_script(script_name: str, args: List[str]) -> Dict[str, Any]:
    """
    Run a memory script and return the result
    
    Args:
        script_name: Name of the script to run (e.g., 'memory_search.py')
        args: Command line arguments for the script
        
    Returns:
        Dictionary with success status and data/error
    """
    script_dir = get_script_dir()
    script_path = script_dir / "scripts" / script_name
    
    # Ensure we're using the virtual environment Python
    venv_python = script_dir / ".venv" / "bin" / "python"
    if not venv_python.exists():
        return {
            "success": False,
            "error": f"Virtual environment not found at {venv_python}. Please run setup.sh first."
        }
    
    # Build the full command
    cmd = [str(venv_python), str(script_path)] + args
    
    try:
        # Run the script
        result = subprocess.run(
            cmd,
            cwd=str(script_dir),
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            # Try to parse JSON output
            try:
                data = json.loads(result.stdout)
                return {"success": True, "data": data}
            except json.JSONDecodeError:
                # Return raw output if not JSON
                return {"success": True, "data": {"output": result.stdout.strip()}}
        else:
            return {
                "success": False,
                "error": f"Script failed with code {result.returncode}: {result.stderr.strip()}"
            }
            
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "Script timed out after 30 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to execute script: {str(e)}"
        }

def memory_search(query: str, limit: int = 10, min_score: float = 0.0, category: str = None) -> Dict[str, Any]:
    """Search memories using semantic similarity"""
    args = ["--query", query, "--limit", str(limit), "--min-score", str(min_score)]
    
    if category:
        args.extend(["--category", category])
    
    return run_memory_script("memory_search_wrapper.py", args)

def memory_store(text: str, category: str = "other", importance: float = 0.5, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """Store text in memory with semantic embedding"""
    args = ["--text", text, "--category", category, "--importance", str(importance)]
    
    if metadata:
        args.extend(["--metadata", json.dumps(metadata)])
    
    return run_memory_script("memory_store_wrapper.py", args)

def handle_tool_call(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle a tool call from OpenClaw
    
    Args:
        tool_name: Name of the tool being called
        parameters: Parameters passed to the tool
        
    Returns:
        Tool execution result
    """
    try:
        if tool_name == "memory_search":
            return memory_search(
                query=parameters["query"],
                limit=parameters.get("limit", 10),
                min_score=parameters.get("min_score", 0.0),
                category=parameters.get("category")
            )
        
        elif tool_name == "memory_store":
            return memory_store(
                text=parameters["text"],
                category=parameters.get("category", "other"),
                importance=parameters.get("importance", 0.5),
                metadata=parameters.get("metadata")
            )
        
        else:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
            
    except KeyError as e:
        return {
            "success": False,
            "error": f"Missing required parameter: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Tool execution failed: {str(e)}"
        }

def main():
    """Main entry point when called from OpenClaw"""
    if len(sys.argv) < 3:
        print(json.dumps({
            "success": False,
            "error": "Usage: plugin.py <tool_name> <parameters_json>"
        }))
        sys.exit(1)
    
    tool_name = sys.argv[1]
    
    try:
        parameters = json.loads(sys.argv[2])
    except json.JSONDecodeError as e:
        print(json.dumps({
            "success": False,
            "error": f"Invalid JSON parameters: {str(e)}"
        }))
        sys.exit(1)
    
    result = handle_tool_call(tool_name, parameters)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()