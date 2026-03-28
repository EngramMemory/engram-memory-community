#!/usr/bin/env python3
"""Redirect — MCP server has moved to mcp/server.py"""
import os, sys
sys.exit(os.execvp(sys.executable, [sys.executable, os.path.join(os.path.dirname(__file__), "..", "mcp", "server.py")] + sys.argv[1:]))
