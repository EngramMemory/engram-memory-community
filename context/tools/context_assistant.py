#!/usr/bin/env python3
"""
Engram Context Assistant

Natural language interface for context system. Allows developers to ask
questions about their codebase in plain English and get intelligent responses
based on context files and semantic search.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import click
from dataclasses import dataclass

# Import our context tools
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "cli"))
sys.path.append(str(Path(__file__).parent))

from context_manager import ContextManager

# Skip semantic search for now - will work with text search only
HAS_SEMANTIC_SEARCH = False

logger = logging.getLogger(__name__)


@dataclass
class ContextResponse:
    """Response from context assistant."""
    answer: str
    sources: List[str]
    confidence: float
    suggestions: List[str]


class ContextAssistant:
    """Natural language interface for context system."""
    
    def __init__(self, project_root: str = None):
        """Initialize context assistant."""
        self.context_manager = ContextManager(project_root)
        self.semantic_engine = None  # Will be enabled when dependencies are available
        self.project_root = self.context_manager.project_root
        
        # Common question patterns and their mappings
        self.question_patterns = {
            "authentication": ["auth", "login", "jwt", "token", "password", "session"],
            "database": ["db", "database", "schema", "model", "migration", "table"],
            "api": ["api", "endpoint", "route", "rest", "graphql"],
            "frontend": ["ui", "component", "react", "vue", "angular", "css"],
            "backend": ["server", "backend", "service", "microservice"],
            "deployment": ["deploy", "docker", "container", "kubernetes", "build"],
            "testing": ["test", "spec", "unit", "integration", "e2e"],
            "debugging": ["debug", "error", "bug", "issue", "troubleshoot"]
        }
    
    def _classify_question(self, question: str) -> List[str]:
        """Classify question type based on keywords."""
        question_lower = question.lower()
        categories = []
        
        for category, keywords in self.question_patterns.items():
            if any(keyword in question_lower for keyword in keywords):
                categories.append(category)
        
        return categories if categories else ["general"]
    
    def _extract_keywords(self, question: str) -> List[str]:
        """Extract relevant keywords from question."""
        # Simple keyword extraction - could be enhanced with NLP
        stop_words = {'how', 'what', 'where', 'when', 'why', 'who', 'is', 'are', 'do', 'does', 
                     'can', 'should', 'would', 'will', 'the', 'a', 'an', 'and', 'or', 'but'}
        
        words = question.lower().replace('?', '').split()
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        return keywords[:5]  # Limit to top 5 keywords
    
    async def ask_question(self, question: str) -> ContextResponse:
        """Process natural language question and provide context-based answer."""
        print(f"🤔 Processing question: {question}")
        
        # Classify question and extract keywords
        categories = self._classify_question(question)
        keywords = self._extract_keywords(question)
        
        print(f"   Categories: {', '.join(categories)}")
        print(f"   Keywords: {', '.join(keywords)}")
        
        # Search using multiple strategies
        sources = []
        content_pieces = []
        
        # 1. Text search with keywords - try multiple search strategies
        text_results = []
        
        # Search with individual keywords first
        for keyword in keywords[:3]:  # Use top 3 keywords
            results = self.context_manager.search_context(keyword, limit=2)
            text_results.extend(results)
        
        # Also search with combined keywords
        if keywords:
            combined_query = ' '.join(keywords[:2])  # Use top 2 keywords
            results = self.context_manager.search_context(combined_query, limit=3)
            text_results.extend(results)
        
        # Remove duplicates
        seen_files = set()
        unique_results = []
        for result in text_results:
            if result.file_path not in seen_files:
                seen_files.add(result.file_path)
                unique_results.append(result)
        
        text_results = unique_results[:3]  # Limit to top 3
        print(f"   Text search results: {len(text_results)}")
        
        for result in text_results:
            sources.append(f"{result.file_path} (text search)")
            content_pieces.append({
                "source": result.file_path,
                "content": result.snippet,
                "relevance": result.relevance_score,
                "method": "text"
            })
        
        # 2. Semantic search with full question (if available)
        if self.semantic_engine:
            try:
                semantic_results = await self.semantic_engine.search_semantic(question, limit=3, threshold=0.2)
                for result in semantic_results:
                    sources.append(f"{result.file_path} (semantic)")
                    content_pieces.append({
                        "source": result.file_path,
                        "content": result.snippet,
                        "relevance": result.similarity_score,
                        "method": "semantic"
                    })
            except Exception as e:
                # Semantic search not available, continue with text search only
                pass
        
        # 3. Category-specific file search
        for category in categories:
            category_file = f"{category}.md"
            category_path = self.context_manager.context_dir / category_file
            if category_path.exists():
                with open(category_path, 'r') as f:
                    content = f.read()
                    # Extract relevant section
                    snippet = self._extract_relevant_section(content, keywords)
                    sources.append(f"{category_file} (category match)")
                    content_pieces.append({
                        "source": category_file,
                        "content": snippet,
                        "relevance": 0.8,
                        "method": "category"
                    })
        
        # Generate answer and suggestions
        answer, confidence, suggestions = self._generate_answer(question, content_pieces, categories)
        
        return ContextResponse(
            answer=answer,
            sources=list(set(sources)),  # Remove duplicates
            confidence=confidence,
            suggestions=suggestions
        )
    
    def _extract_relevant_section(self, content: str, keywords: List[str], context_size: int = 400) -> str:
        """Extract the most relevant section from content based on keywords."""
        content_lower = content.lower()
        
        # Find the position with the most keyword matches
        best_pos = 0
        best_score = 0
        
        for i in range(0, len(content) - context_size, 50):
            section = content_lower[i:i + context_size]
            score = sum(1 for keyword in keywords if keyword in section)
            if score > best_score:
                best_score = score
                best_pos = i
        
        # Extract section around best position
        start = max(0, best_pos - 50)
        end = min(len(content), best_pos + context_size + 50)
        
        section = content[start:end].strip()
        
        # Add ellipsis if needed
        if start > 0:
            section = "..." + section
        if end < len(content):
            section = section + "..."
        
        return section
    
    def _generate_answer(self, question: str, content_pieces: List[Dict], categories: List[str]) -> Tuple[str, float, List[str]]:
        """Generate answer based on found content."""
        if not content_pieces:
            return ("I couldn't find specific information about that in the context files. "
                   "Try checking if the relevant context files exist or need updating."), 0.1, []
        
        # Sort content by relevance
        content_pieces.sort(key=lambda x: x['relevance'], reverse=True)
        
        # Build answer based on content type and question
        answer_parts = []
        confidence = 0.0
        suggestions = []
        
        # Start with the most relevant piece
        top_content = content_pieces[0]
        
        if "how" in question.lower():
            answer_parts.append("Based on the context files, here's how this works:\n")
        elif "what" in question.lower():
            answer_parts.append("Based on the context documentation:\n")
        elif "where" in question.lower():
            answer_parts.append("According to the project structure:\n")
        else:
            answer_parts.append("From the context files:\n")
        
        # Add content from top sources
        used_sources = set()
        for content in content_pieces[:3]:  # Use top 3 results
            if content['source'] not in used_sources:
                answer_parts.append(f"\n📄 From {content['source']}:")
                answer_parts.append(content['content'])
                used_sources.add(content['source'])
                confidence += content['relevance']
        
        confidence = min(confidence / len(used_sources), 1.0)
        
        # Add suggestions based on categories
        if "authentication" in categories:
            suggestions.extend([
                "Check authentication.md for auth flows",
                "Look for JWT token patterns",
                "Review security middleware configuration"
            ])
        
        if "database" in categories:
            suggestions.extend([
                "Check database migration files", 
                "Review model definitions",
                "Look at schema documentation"
            ])
        
        if "api" in categories:
            suggestions.extend([
                "Check API route definitions",
                "Review endpoint documentation",
                "Look at request/response schemas"
            ])
        
        # Generic suggestions if confidence is low
        if confidence < 0.5:
            suggestions.extend([
                "Try updating context files with more details",
                "Search for specific file names or functions",
                "Check if the information exists in code comments"
            ])
        
        return "\n".join(answer_parts), confidence, suggestions[:5]
    
    def get_interactive_session(self):
        """Start interactive Q&A session."""
        print("🤖 Engram Context Assistant")
        print("   Ask questions about your codebase in natural language")
        print("   Type 'quit', 'exit', or 'q' to end the session\n")
        
        while True:
            try:
                question = input("❓ Ask a question: ").strip()
                
                if question.lower() in ['quit', 'exit', 'q', '']:
                    print("👋 Goodbye!")
                    break
                
                # Process question
                response = asyncio.run(self.ask_question(question))
                
                print(f"\n💡 Answer (confidence: {response.confidence:.2f}):")
                print(response.answer)
                
                if response.sources:
                    print(f"\n📚 Sources:")
                    for source in response.sources:
                        print(f"  • {source}")
                
                if response.suggestions:
                    print(f"\n🔍 Suggestions:")
                    for suggestion in response.suggestions:
                        print(f"  • {suggestion}")
                
                print("\n" + "─" * 60 + "\n")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                print("Please try rephrasing your question.\n")


@click.group()
@click.pass_context
def cli(ctx):
    """Engram Context Assistant - Natural Language Interface"""
    ctx.ensure_object(dict)


@cli.command()
@click.argument('question', nargs=-1, required=True)
@click.option('--project', default='.', help='Project root directory')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed analysis')
@click.pass_context
def ask(ctx, question, project, verbose):
    """Ask a question about your codebase."""
    assistant = ContextAssistant(project)
    question_str = ' '.join(question)
    
    response = asyncio.run(assistant.ask_question(question_str))
    
    print(f"💡 Answer (confidence: {response.confidence:.2f}):")
    print(response.answer)
    
    if verbose or response.sources:
        print(f"\n📚 Sources:")
        for source in response.sources:
            print(f"  • {source}")
    
    if verbose or response.suggestions:
        print(f"\n🔍 Suggestions:")
        for suggestion in response.suggestions:
            print(f"  • {suggestion}")


@cli.command()
@click.option('--project', default='.', help='Project root directory')
@click.pass_context
def interactive(ctx, project):
    """Start interactive Q&A session."""
    assistant = ContextAssistant(project)
    assistant.get_interactive_session()


@cli.command()
@click.option('--project', default='.', help='Project root directory')
@click.pass_context
def examples(ctx, project):
    """Show example questions you can ask."""
    print("🤖 Engram Context Assistant - Example Questions\n")
    
    examples = [
        ("How does authentication work?", "Learn about auth flows and JWT patterns"),
        ("Where are the API endpoints defined?", "Find API route definitions and structure"),
        ("What is the database schema?", "Get database structure and model information"),
        ("How do I debug Docker issues?", "Find troubleshooting tips for containers"),
        ("What are the frontend components?", "Learn about UI structure and components"),
        ("How does deployment work?", "Understand build and deployment processes"),
        ("Where are the tests located?", "Find testing patterns and structure"),
        ("How do I add a new feature?", "Learn development workflow and patterns")
    ]
    
    for i, (question, description) in enumerate(examples, 1):
        print(f"{i}. '{question}'")
        print(f"   {description}\n")
    
    print("💡 Tips:")
    print("  • Ask specific questions about your codebase")
    print("  • Use natural language - don't worry about exact syntax")
    print("  • Try different phrasings if you don't get good results")
    print("  • Use --verbose for more detailed analysis")


if __name__ == '__main__':
    cli()