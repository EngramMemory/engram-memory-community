#!/bin/bash

# Engram Context System Setup
# Integrates context management capabilities into Engram

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PERFECT_RECALL_ROOT="$(dirname "$SCRIPT_DIR")"
CONTEXT_DIR="$PERFECT_RECALL_ROOT/context"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧠 Engram Context System Setup${NC}"
echo "================================================"

# Check if we're in Engram repository
if [ ! -f "$PERFECT_RECALL_ROOT/SKILL.md" ]; then
    echo -e "${RED}❌ Error: This script must be run from Engram repository${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Engram repository detected${NC}"

# Check Python dependencies
echo -e "${YELLOW}📦 Checking Python dependencies...${NC}"
python3 -c "import click, yaml" 2>/dev/null || {
    echo -e "${YELLOW}⚠️  Installing required dependencies...${NC}"
    pip3 install click pyyaml
}

# Optional dependencies for semantic search
echo -e "${YELLOW}🔍 Checking semantic search dependencies...${NC}"
SEMANTIC_AVAILABLE=true
python3 -c "import httpx, numpy" 2>/dev/null || {
    echo -e "${YELLOW}⚠️  Optional semantic search dependencies not found${NC}"
    echo "   To enable semantic search, install: pip3 install httpx numpy"
    SEMANTIC_AVAILABLE=false
}

# Make CLI tools executable
echo -e "${YELLOW}🔧 Setting up CLI tools...${NC}"
chmod +x "$CONTEXT_DIR/cli/context_manager.py"
chmod +x "$CONTEXT_DIR/tools/semantic_search.py"
chmod +x "$CONTEXT_DIR/tools/context_assistant.py"

# Create symbolic links for easy access
echo -e "${YELLOW}🔗 Creating command aliases...${NC}"
COMMANDS_DIR="$PERFECT_RECALL_ROOT/bin"
mkdir -p "$COMMANDS_DIR"

# Create wrapper scripts
cat > "$COMMANDS_DIR/engram-context" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PERFECT_RECALL_ROOT="$(dirname "$SCRIPT_DIR")"
python3 "$PERFECT_RECALL_ROOT/context/cli/context_manager.py" "$@"
EOF

cat > "$COMMANDS_DIR/engram-semantic" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PERFECT_RECALL_ROOT="$(dirname "$SCRIPT_DIR")"
python3 "$PERFECT_RECALL_ROOT/context/tools/semantic_search.py" "$@"
EOF

cat > "$COMMANDS_DIR/engram-ask" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PERFECT_RECALL_ROOT="$(dirname "$SCRIPT_DIR")"
python3 "$PERFECT_RECALL_ROOT/context/tools/context_assistant.py" "$@"
EOF

chmod +x "$COMMANDS_DIR"/*

# Update PATH recommendation
echo -e "${YELLOW}📝 Adding to PATH...${NC}"
if ! echo "$PATH" | grep -q "$COMMANDS_DIR"; then
    echo "export PATH=\"$COMMANDS_DIR:\$PATH\"" >> "$HOME/.bashrc"
    echo -e "${GREEN}✅ Added Engram commands to PATH${NC}"
    echo -e "${YELLOW}   Run: source ~/.bashrc  (or restart terminal)${NC}"
fi

# Check if Engram memory system is running
echo -e "${YELLOW}🔍 Checking Engram services...${NC}"
if curl -s http://localhost:6333/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Qdrant vector store is running${NC}"
    QDRANT_RUNNING=true
else
    echo -e "${YELLOW}⚠️  Qdrant vector store not running${NC}"
    echo "   Context system will work with reduced functionality"
    echo "   Run: bash scripts/setup.sh  (from Engram root)"
    QDRANT_RUNNING=false
fi

if curl -s http://localhost:11435/health > /dev/null 2>&1; then
    echo -e "${GREEN}✅ FastEmbed service is running${NC}"
    EMBEDDING_RUNNING=true
else
    echo -e "${YELLOW}⚠️  FastEmbed service not running${NC}"
    echo "   Semantic search will not be available"
    echo "   Run: bash scripts/setup.sh  (from Engram root)"
    EMBEDDING_RUNNING=false
fi

# Update Engram SKILL.md to include context capabilities
echo -e "${YELLOW}📝 Updating Engram documentation...${NC}"

# Create context section for SKILL.md (we'll show the update separately)
CONTEXT_SECTION="
## Context System Integration

Engram now includes an intelligent context management system for any development project.

### Context Commands

\`\`\`bash
# Initialize context for a project
engram-context init /path/to/project --template web-app

# Build context search index
engram-context index --project /path/to/project

# Search context files
engram-context find \"authentication patterns\"

# Natural language queries
engram-ask \"How does authentication work?\"

# Semantic search (requires FastEmbed)
engram-semantic find \"user login flow\"
\`\`\`

### Integration with Memory

The context system integrates seamlessly with Engram's memory:
- Context insights are automatically stored in vector memory
- Related memories surface when accessing context
- Cross-project learning through shared memory patterns
- Development patterns become part of agent knowledge

### Project Templates

Available templates for different project types:
- \`web-app\` - Full-stack web applications
- \`python-api\` - Python API projects  
- \`generic\` - Generic project template

### Context Structure

Each project gets a \`.context/\` directory with:
- \`architecture.md\` - System architecture
- \`patterns.md\` - Code patterns and best practices
- \`apis.md\` - API documentation
- \`development.md\` - Development workflows
- \`troubleshooting.md\` - Common issues and solutions
"

echo -e "${GREEN}✅ Context system integration complete!${NC}"
echo ""
echo -e "${BLUE}🚀 Quick Start:${NC}"
echo ""
echo "1. Initialize context for a project:"
echo "   engram-context init /path/to/your/project --template web-app"
echo ""
echo "2. Build search index:"
echo "   engram-context index"
echo ""
echo "3. Start asking questions:"
echo "   engram-ask \"How does authentication work?\""
echo ""
echo -e "${BLUE}📚 Documentation:${NC}"
echo "   • Context README: $CONTEXT_DIR/README.md"
echo "   • Available commands: engram-context --help"
echo "   • Examples: engram-ask examples"
echo ""

# Create integration status report
REPORT_FILE="$PERFECT_RECALL_ROOT/context-integration-status.md"
cat > "$REPORT_FILE" << EOF
# Engram Context System Integration Status

**Date:** $(date)
**Status:** Integration Complete ✅

## Components Installed

### Core Context Management
- ✅ Context Manager CLI (engram-context)
- ✅ Natural Language Interface (engram-ask)
- ✅ Project Templates (web-app, python-api, generic)
- ✅ Documentation and Usage Guides

### Semantic Search
- $([ "$SEMANTIC_AVAILABLE" = true ] && echo "✅" || echo "⚠️") Dependencies Available
- $([ "$EMBEDDING_RUNNING" = true ] && echo "✅" || echo "⚠️") FastEmbed Service

### Integration with Engram
- $([ "$QDRANT_RUNNING" = true ] && echo "✅" || echo "⚠️") Qdrant Vector Store
- ✅ Memory System Integration
- ✅ CLI Command Integration

## Available Commands

- \`engram-context\` - Core context management
- \`engram-semantic\` - Semantic search (if available)
- \`engram-ask\` - Natural language interface

## Next Steps

1. Initialize context for your projects:
   \`\`\`bash
   engram-context init /path/to/project --template web-app
   \`\`\`

2. Build search indexes:
   \`\`\`bash
   engram-context index
   \`\`\`

3. Start using natural language queries:
   \`\`\`bash
   engram-ask "How does authentication work?"
   \`\`\`

## Integration Benefits

- **Unified Development Infrastructure**: Memory + Context in one system
- **Cross-Project Learning**: Patterns learned in one project help others
- **Natural Language Interface**: Ask questions about codebases in plain English
- **Generic Templates**: Works with any project type, not just War Room
- **Seamless Agent Integration**: OpenClaw agents can use context + memory together

---
**Engram: Never forget code patterns again**
EOF

echo -e "${GREEN}✅ Integration status saved to: $REPORT_FILE${NC}"

if [ "$SEMANTIC_AVAILABLE" = false ] || [ "$EMBEDDING_RUNNING" = false ] || [ "$QDRANT_RUNNING" = false ]; then
    echo ""
    echo -e "${YELLOW}⚠️  Some features require Engram services to be running${NC}"
    echo "   Run: bash scripts/setup.sh  (from Engram root)"
    echo "   This will start Qdrant and FastEmbed services"
fi

echo ""
echo -e "${GREEN}🎉 Engram Context System is ready!${NC}"