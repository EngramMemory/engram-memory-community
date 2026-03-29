#!/usr/bin/env python3
"""
Engram OpenClaw Plugin

Bridges OpenClaw's tool calling system with FastEmbed + Qdrant backend.
Handles: memory_store, memory_search, memory_forget, context_search, context_ask
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


def run_script(script_path: str, args: List[str]) -> Dict[str, Any]:
    """Run a Python script via the venv and return the result."""
    script_dir = get_script_dir()
    full_path = script_dir / script_path

    venv_python = script_dir / ".venv" / "bin" / "python"
    if not venv_python.exists():
        # Fall back to system python3
        venv_python = Path("python3")

    cmd = [str(venv_python), str(full_path)] + args

    try:
        result = subprocess.run(
            cmd, cwd=str(script_dir),
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                return {"success": True, "data": data}
            except json.JSONDecodeError:
                return {"success": True, "data": {"output": result.stdout.strip()}}
        else:
            return {"success": False, "error": f"Script failed: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Script timed out after 30 seconds"}
    except Exception as e:
        return {"success": False, "error": f"Failed to execute: {str(e)}"}


# ── Memory Tools ────────────────────────────────────────────────

def memory_search(query: str, limit: int = 10, min_score: float = 0.0, category: str = None) -> Dict[str, Any]:
    args = ["--query", query, "--limit", str(limit), "--min-score", str(min_score)]
    if category:
        args.extend(["--category", category])
    return run_script("scripts/memory_search_wrapper.py", args)


def memory_store(text: str, category: str = "other", importance: float = 0.5, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    args = ["--text", text, "--category", category, "--importance", str(importance)]
    if metadata:
        args.extend(["--metadata", json.dumps(metadata)])
    return run_script("scripts/memory_store_wrapper.py", args)


def memory_forget(query: str = None, memory_id: str = None) -> Dict[str, Any]:
    """Delete a memory by search match or ID."""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(host="localhost", port=6333)

        if memory_id:
            client.delete(collection_name="agent-memory", points_selector=[memory_id])
            return {"success": True, "deleted": memory_id}

        if query:
            result = memory_search(query, limit=1)
            if result.get("success") and result.get("data", {}).get("results"):
                target = result["data"]["results"][0]
                target_id = str(target["id"])
                client.delete(collection_name="agent-memory", points_selector=[target_id])
                return {"success": True, "deleted": target_id, "text": target.get("text", "")[:80]}
            return {"success": False, "error": "No matching memory found"}

        return {"success": False, "error": "Provide query or memory_id"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Context Tools ───────────────────────────────────────────────

def context_search(query: str, project: str = ".", limit: int = 5) -> Dict[str, Any]:
    """Search project context files."""
    return run_script("context/cli/context_manager.py", ["find", query, "--limit", str(limit), "--project", project])


def context_ask(question: str, project: str = ".") -> Dict[str, Any]:
    """Ask a natural language question about the project."""
    return run_script("context/tools/context_assistant.py", ["ask", question, "--project", project])


# ── Tool Dispatcher ─────────────────────────────────────────────

def handle_tool_call(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
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

        elif tool_name == "memory_forget":
            return memory_forget(
                query=parameters.get("query"),
                memory_id=parameters.get("memory_id")
            )

        elif tool_name == "context_search":
            return context_search(
                query=parameters["query"],
                project=parameters.get("project", "."),
                limit=parameters.get("limit", 5)
            )

        elif tool_name == "context_ask":
            return context_ask(
                question=parameters["question"],
                project=parameters.get("project", ".")
            )

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    except KeyError as e:
        return {"success": False, "error": f"Missing required parameter: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Tool execution failed: {str(e)}"}


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"success": False, "error": "Usage: plugin.py <tool_name> <parameters_json>"}))
        sys.exit(1)

    tool_name = sys.argv[1]
    try:
        parameters = json.loads(sys.argv[2])
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {str(e)}"}))
        sys.exit(1)

    result = handle_tool_call(tool_name, parameters)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
