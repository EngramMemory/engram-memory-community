#!/usr/bin/env python3
"""
Engram Context Manager

Generic context management system extracted from War Room and generalized
for any development project. Provides intelligent codebase navigation,
pattern discovery, and semantic search capabilities.
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
import yaml
from dataclasses import dataclass, asdict

# Try to import optional dependencies
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

logger = logging.getLogger(__name__)


@dataclass
class ContextFile:
    """Represents a context file."""
    path: str
    content_hash: str
    metadata: Dict[str, Any]
    indexed_at: str


@dataclass
class SearchResult:
    """Search result from context system."""
    file_path: str
    relevance_score: float
    snippet: str
    metadata: Dict[str, Any]


class ContextManager:
    """Core context management for any development project."""
    
    def __init__(self, project_root: str = None):
        """Initialize context manager for a project."""
        if project_root:
            self.project_root = Path(project_root).resolve()
        else:
            # Try to find project root by looking for common markers
            self.project_root = self._find_project_root()
        
        self.context_dir = self.project_root / ".context"
        self.metadata_file = self.context_dir / "metadata.yaml"
        self.index_file = self.context_dir / "index.db"
        
        # Ensure context directory exists
        self.context_dir.mkdir(parents=True, exist_ok=True)
    
    def _find_project_root(self) -> Path:
        """Find project root by looking for common markers."""
        current = Path.cwd()
        markers = ['.git', 'package.json', 'pyproject.toml', 'go.mod', 'Cargo.toml']
        
        while current != current.parent:
            for marker in markers:
                if (current / marker).exists():
                    return current
            current = current.parent
        
        # Fallback to current directory
        return Path.cwd()
    
    def init_project(self, template: str = "generic") -> Dict[str, Any]:
        """Initialize context system for a project."""
        print(f"🚀 Initializing context system for {self.project_root}")
        
        # Create metadata
        metadata = {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "description": f"Context management system for {self.project_root.name}",
            "template": template,
            "structure": {
                "architecture": "System architecture and service organization",
                "patterns": "Code patterns, auth flows, and standards",
                "apis": "Endpoint documentation and API patterns",
                "frontend": "Frontend structure and component organization", 
                "backend": "Backend architecture and patterns",
                "development": "Development workflows and troubleshooting"
            },
            "indexing": {
                "last_updated": None,
                "files_indexed": 0,
                "embedding_model": "text-embedding-ada-002"  # Default, can be changed
            }
        }
        
        # Save metadata
        with open(self.metadata_file, 'w') as f:
            yaml.dump(metadata, f, default_flow_style=False)
        
        # Create template files based on project type
        template_files = self._get_template_files(template)
        created_files = []
        
        for file_name, content in template_files.items():
            file_path = self.context_dir / file_name
            if not file_path.exists():
                with open(file_path, 'w') as f:
                    f.write(content)
                created_files.append(file_name)
        
        print(f"✅ Created context structure with {len(created_files)} files")
        print("📝 Edit the generated files to document your project's patterns")
        print(f"💾 Run 'engram context index' to build search index")
        
        return {
            "project_root": str(self.project_root),
            "template": template,
            "files_created": created_files,
            "next_steps": [
                "Edit context files to match your project",
                "Run 'engram context index' to build search index",
                "Start using 'engram context find' to search"
            ]
        }
    
    def _get_template_files(self, template: str) -> Dict[str, str]:
        """Get template files for project type."""
        
        # Common header for all templates
        header = f"""---
description: "Context documentation for {self.project_root.name}"
template: "{template}"
created: "{datetime.now().isoformat()}"
---

"""
        
        if template == "web-app":
            return {
                "architecture.md": header + """# System Architecture

## Overview
This is a web application with frontend and backend components.

## Services
- Frontend: Web interface (port 3000)
- Backend: API server (port 8000) 
- Database: PostgreSQL (port 5432)

## Authentication
- JWT tokens for API authentication
- Session-based authentication for web interface

## Deployment
- Docker containers for all services
- nginx reverse proxy for routing
""",
                "patterns.md": header + """# Development Patterns

## Authentication Flow
1. User submits credentials to /auth/login
2. Server validates and returns JWT token
3. Client includes token in Authorization header
4. Server validates token on protected routes

## API Patterns
- RESTful endpoints under /api/v1/
- Consistent error response format
- Request/response validation with schemas

## Frontend Patterns  
- React components in components/ directory
- Global state management with Context/Redux
- API calls in services/ directory

## Database Patterns
- Models in models/ directory
- Migrations in migrations/ directory
- Connection pooling for performance
""",
                "apis.md": header + """# API Documentation

## Authentication Endpoints
- POST /auth/login - User login
- POST /auth/logout - User logout  
- GET /auth/me - Get current user

## Main Endpoints
- GET /api/v1/users - List users
- POST /api/v1/users - Create user
- GET /api/v1/users/{id} - Get user by ID

## Error Responses
All errors return JSON with error message and status code.
""",
                "development.md": header + """# Development Workflow

## Getting Started
1. Clone repository
2. Install dependencies: npm install / pip install -r requirements.txt
3. Setup database: Run migrations
4. Start development server

## Common Commands
- Start dev server: npm run dev / python app.py
- Run tests: npm test / pytest
- Build for production: npm run build

## Debugging
- Check logs in logs/ directory
- Use browser dev tools for frontend issues
- Use debugger breakpoints for backend issues
""",
                "troubleshooting.md": header + """# Troubleshooting Guide

## Common Issues

### Authentication Errors
- Check JWT token expiration
- Verify token format and signature
- Check user permissions

### Database Connection Issues
- Verify database is running
- Check connection string configuration
- Verify network connectivity

### Frontend Build Issues
- Clear node_modules and reinstall
- Check for TypeScript errors
- Verify environment variables
"""
            }
        elif template == "python-api":
            return {
                "architecture.md": header + """# Python API Architecture

## Overview
FastAPI/Django-based API server with database backend.

## Components
- API Server: FastAPI/Django (port 8000)
- Database: PostgreSQL/SQLite
- Background Tasks: Celery/RQ (optional)
- Cache: Redis (optional)

## Authentication
- JWT tokens or API keys
- Role-based access control
- Rate limiting
""",
                "patterns.md": header + """# Python API Patterns

## Project Structure
```
app/
├── models/          # Database models
├── schemas/         # Pydantic schemas (FastAPI) / Serializers (Django)
├── routes/          # API endpoints
├── services/        # Business logic
├── utils/          # Utility functions
└── tests/          # Test files
```

## Authentication
- JWT token validation middleware
- Dependency injection for auth
- Permission decorators/dependencies

## Database Patterns
- SQLAlchemy ORM (FastAPI) / Django ORM
- Async database operations
- Connection pooling
- Migration management

## Error Handling
- Custom exception classes
- Global exception handlers
- Structured error responses
""",
                "apis.md": header + """# API Endpoints

## Authentication
- POST /auth/token - Get access token
- POST /auth/refresh - Refresh token
- GET /auth/me - Current user info

## Core Resources
- GET /api/v1/items - List items
- POST /api/v1/items - Create item
- GET /api/v1/items/{id} - Get item
- PUT /api/v1/items/{id} - Update item
- DELETE /api/v1/items/{id} - Delete item

## Response Format
```json
{
  "data": {...},
  "message": "Success",
  "status": "ok"
}
```
""",
                "development.md": header + """# Python Development Workflow

## Setup
1. Create virtual environment: python -m venv venv
2. Activate: source venv/bin/activate (Linux/Mac) or venv\\Scripts\\activate (Windows)
3. Install dependencies: pip install -r requirements.txt
4. Setup database: alembic upgrade head / python manage.py migrate
5. Run server: uvicorn main:app --reload / python manage.py runserver

## Testing
- Run tests: pytest / python manage.py test
- Coverage: pytest --cov=app
- Linting: flake8, black, mypy

## Database Operations
- Create migration: alembic revision --autogenerate -m "description"
- Apply migrations: alembic upgrade head
- Reset database: alembic downgrade base && alembic upgrade head
"""
            }
        else:  # generic template
            return {
                "architecture.md": header + """# Project Architecture

## Overview
Describe your project's overall architecture here.

## Components
List the main components/modules of your system.

## Data Flow
Describe how data flows through your system.

## External Dependencies
List external services and APIs your project depends on.
""",
                "patterns.md": header + """# Code Patterns

## Naming Conventions
Document your naming conventions for files, functions, variables.

## Code Organization
Describe how code is organized in your project.

## Common Patterns
Document recurring patterns in your codebase.

## Best Practices
List project-specific best practices and guidelines.
""",
                "development.md": header + """# Development Guide

## Getting Started
Steps to set up development environment.

## Common Tasks
Document common development tasks and commands.

## Testing
How to run tests and what testing practices to follow.

## Debugging
Common debugging techniques and tools for your project.
"""
            }
    
    def build_index(self) -> Dict[str, Any]:
        """Build search index for context files."""
        print("🔍 Building context search index...")
        
        # Initialize SQLite index database
        conn = sqlite3.connect(self.index_file)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS context_files (
                path TEXT PRIMARY KEY,
                content_hash TEXT,
                content TEXT,
                metadata TEXT,
                indexed_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_content ON context_files(content)")
        
        # Index all context files
        context_files = list(self.context_dir.glob("*.md"))
        indexed_count = 0
        
        for file_path in context_files:
            if file_path.name.startswith('.'):
                continue
                
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Calculate content hash
            content_hash = hashlib.md5(content.encode('utf-8')).hexdigest()
            
            # Extract metadata from frontmatter
            metadata = {}
            if content.startswith('---'):
                try:
                    frontmatter_end = content.find('---', 3)
                    if frontmatter_end > 0:
                        frontmatter = content[3:frontmatter_end].strip()
                        metadata = yaml.safe_load(frontmatter)
                        content = content[frontmatter_end + 3:].strip()
                except:
                    pass
            
            # Check if file needs reindexing
            cursor = conn.execute(
                "SELECT content_hash FROM context_files WHERE path = ?",
                (str(file_path.relative_to(self.context_dir)),)
            )
            existing = cursor.fetchone()
            
            if not existing or existing[0] != content_hash:
                # Index the file
                conn.execute("""
                    INSERT OR REPLACE INTO context_files 
                    (path, content_hash, content, metadata, indexed_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    str(file_path.relative_to(self.context_dir)),
                    content_hash,
                    content,
                    json.dumps(metadata),
                    datetime.now().isoformat()
                ))
                indexed_count += 1
        
        conn.commit()
        conn.close()
        
        # Update metadata
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                metadata = yaml.safe_load(f)
            metadata['indexing']['last_updated'] = datetime.now().isoformat()
            metadata['indexing']['files_indexed'] = len(context_files)
            with open(self.metadata_file, 'w') as f:
                yaml.dump(metadata, f, default_flow_style=False)
        
        print(f"✅ Indexed {indexed_count} files, {len(context_files)} total")
        return {
            "files_indexed": indexed_count,
            "total_files": len(context_files),
            "index_updated": datetime.now().isoformat()
        }
    
    def search_context(self, query: str, limit: int = 10) -> List[SearchResult]:
        """Search context files using text search."""
        if not self.index_file.exists():
            print("⚠️  No search index found. Run 'engram context index' first.")
            return []
        
        conn = sqlite3.connect(self.index_file)
        
        # Perform full-text search
        cursor = conn.execute("""
            SELECT path, content, metadata
            FROM context_files
            WHERE content LIKE ?
            ORDER BY 
                CASE 
                    WHEN LOWER(content) LIKE LOWER(?) THEN 1
                    WHEN LOWER(path) LIKE LOWER(?) THEN 2
                    ELSE 3
                END,
                LENGTH(content)
            LIMIT ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
        
        results = []
        for row in cursor.fetchall():
            path, content, metadata_json = row
            try:
                metadata = json.loads(metadata_json)
            except:
                metadata = {}
            
            # Extract snippet around match
            content_lower = content.lower()
            query_lower = query.lower()
            match_pos = content_lower.find(query_lower)
            
            if match_pos >= 0:
                start = max(0, match_pos - 100)
                end = min(len(content), match_pos + len(query) + 100)
                snippet = content[start:end].strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
            else:
                snippet = content[:200] + "..." if len(content) > 200 else content
            
            # Simple relevance scoring based on match position and frequency
            relevance = 1.0
            if query_lower in path.lower():
                relevance += 0.5
            if query_lower in content_lower:
                relevance += content_lower.count(query_lower) * 0.1
            
            results.append(SearchResult(
                file_path=path,
                relevance_score=min(relevance, 1.0),
                snippet=snippet,
                metadata=metadata
            ))
        
        conn.close()
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Get context system status."""
        if not self.context_dir.exists():
            return {"status": "not_initialized", "message": "Context system not initialized"}
        
        status = {
            "status": "initialized",
            "project_root": str(self.project_root),
            "context_dir": str(self.context_dir),
            "metadata": None,
            "index": None,
            "files": []
        }
        
        # Load metadata
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                status["metadata"] = yaml.safe_load(f)
        
        # Check index
        if self.index_file.exists():
            conn = sqlite3.connect(self.index_file)
            cursor = conn.execute("SELECT COUNT(*) FROM context_files")
            count = cursor.fetchone()[0]
            conn.close()
            status["index"] = {
                "exists": True,
                "file_count": count,
                "last_updated": status["metadata"]["indexing"]["last_updated"] if status["metadata"] else None
            }
        else:
            status["index"] = {"exists": False}
        
        # List context files
        status["files"] = [f.name for f in self.context_dir.glob("*.md")]
        
        return status
    
    def validate_context(self) -> Dict[str, Any]:
        """Validate context system structure and content."""
        issues = []
        warnings = []
        
        # Check if initialized
        if not self.context_dir.exists():
            issues.append("Context system not initialized")
            return {"valid": False, "issues": issues, "warnings": warnings}
        
        # Check for required files
        required_files = ["architecture.md", "patterns.md", "development.md"]
        for required_file in required_files:
            file_path = self.context_dir / required_file
            if not file_path.exists():
                warnings.append(f"Recommended file missing: {required_file}")
            elif file_path.stat().st_size < 100:
                warnings.append(f"File appears empty or minimal: {required_file}")
        
        # Check metadata
        if not self.metadata_file.exists():
            issues.append("metadata.yaml missing")
        else:
            try:
                with open(self.metadata_file, 'r') as f:
                    metadata = yaml.safe_load(f)
                
                if not metadata.get('version'):
                    issues.append("metadata.yaml missing version")
                if not metadata.get('structure'):
                    warnings.append("metadata.yaml missing structure definition")
            except Exception as e:
                issues.append(f"Invalid metadata.yaml: {e}")
        
        # Check index
        if not self.index_file.exists():
            warnings.append("Search index not built (run 'engram context index')")
        
        # Check for empty context files
        for file_path in self.context_dir.glob("*.md"):
            if file_path.stat().st_size < 50:
                warnings.append(f"Context file is very small: {file_path.name}")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "file_count": len(list(self.context_dir.glob("*.md"))),
            "project_root": str(self.project_root)
        }


@click.group()
@click.pass_context
def cli(ctx):
    """Engram Context Management System"""
    ctx.ensure_object(dict)


@cli.command()
@click.argument('project_path', default='.')
@click.option('--template', default='generic', help='Project template (generic, web-app, python-api)')
@click.pass_context
def init(ctx, project_path, template):
    """Initialize context system for a project."""
    manager = ContextManager(project_path)
    result = manager.init_project(template)
    
    print(f"\n📁 Project: {result['project_root']}")
    print(f"📋 Template: {result['template']}")
    print(f"📄 Files created: {len(result['files_created'])}")
    
    for step in result['next_steps']:
        print(f"  • {step}")


@cli.command()
@click.option('--project', default='.', help='Project root directory')
@click.pass_context  
def index(ctx, project):
    """Build search index for context files."""
    manager = ContextManager(project)
    result = manager.build_index()
    
    print(f"📊 Indexing complete:")
    print(f"  • New files indexed: {result['files_indexed']}")
    print(f"  • Total files: {result['total_files']}")


@cli.command()
@click.argument('query')
@click.option('--limit', default=5, help='Maximum number of results')
@click.option('--project', default='.', help='Project root directory')
@click.pass_context
def find(ctx, query, limit, project):
    """Search context files."""
    manager = ContextManager(project)
    results = manager.search_context(query, limit)
    
    if not results:
        print(f"🔍 No results found for: {query}")
        return
    
    print(f"🔍 Found {len(results)} results for: {query}\n")
    
    for i, result in enumerate(results, 1):
        print(f"{i}. 📄 {result.file_path} (score: {result.relevance_score:.2f})")
        print(f"   {result.snippet}")
        if result.metadata.get('description'):
            print(f"   💡 {result.metadata['description']}")
        print()


@cli.command()
@click.option('--project', default='.', help='Project root directory')
@click.pass_context
def status(ctx, project):
    """Show context system status."""
    manager = ContextManager(project)
    status = manager.get_status()
    
    print(f"🤖 Engram Context System")
    print(f"📁 Project: {status['project_root']}")
    print(f"📂 Context: {status['context_dir']}")
    print(f"🏷️  Status: {status['status']}")
    
    if status['metadata']:
        meta = status['metadata']
        print(f"📋 Template: {meta.get('template', 'unknown')}")
        print(f"📅 Created: {meta.get('created', 'unknown')}")
    
    if status['index']:
        if status['index']['exists']:
            print(f"🔍 Index: {status['index']['file_count']} files indexed")
            if status['index']['last_updated']:
                print(f"🕒 Last updated: {status['index']['last_updated']}")
        else:
            print("🔍 Index: Not built (run 'engram context index')")
    
    if status['files']:
        print(f"📄 Context files: {', '.join(status['files'])}")


@cli.command()
@click.option('--project', default='.', help='Project root directory')
@click.pass_context
def validate(ctx, project):
    """Validate context system structure."""
    manager = ContextManager(project)
    result = manager.validate_context()
    
    if result['valid']:
        print("✅ Context system is valid")
    else:
        print("❌ Context system has issues")
    
    if result['issues']:
        print("\n🚨 Issues:")
        for issue in result['issues']:
            print(f"  • {issue}")
    
    if result['warnings']:
        print("\n⚠️  Warnings:")
        for warning in result['warnings']:
            print(f"  • {warning}")
    
    print(f"\n📊 Summary:")
    print(f"  • Files: {result['file_count']}")
    print(f"  • Project: {result['project_root']}")


if __name__ == '__main__':
    cli()