#!/bin/bash
# Engram Memory Community Edition — Setup Script
# Deploys Qdrant + FastEmbed and generates OpenClaw configuration

set -euo pipefail

# Resolve repo root before we cd anywhere
ENGRAM_REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Engram Memory Setup${NC}"
echo "Setting up persistent memory for your AI agent..."
echo ""

# Check prerequisites
check_prereq() {
    local cmd=$1
    local name=$2
    if ! command -v "$cmd" &> /dev/null; then
        echo -e "${RED}$name is not installed${NC}"
        echo "Please install $name and run this script again."
        exit 1
    else
        echo -e "${GREEN}$name found${NC}"
    fi
}

echo "Checking prerequisites..."
check_prereq "docker" "Docker"
check_prereq "docker-compose" "Docker Compose"

# Check Docker is running
if ! docker info &> /dev/null; then
    echo -e "${RED}Docker is not running${NC}"
    echo "Please start Docker and run this script again."
    exit 1
fi
echo -e "${GREEN}Docker is running${NC}"

# Get setup directory
SETUP_DIR="${MEMORY_STACK_DIR:-$HOME/engram-stack}"
echo ""
echo -e "${BLUE}Installation directory:${NC} $SETUP_DIR"

# Ask for confirmation
read -p "Continue with setup? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Setup cancelled."
    exit 0
fi

# Create setup directory
mkdir -p "$SETUP_DIR"
cd "$SETUP_DIR"

# Generate docker-compose.yml
echo ""
echo -e "${BLUE}Generating docker-compose.yml...${NC}"

cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:v1.11.3
    container_name: qdrant-memory
    restart: unless-stopped
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage:/qdrant/storage
    environment:
      - QDRANT__SERVICE__HTTP_PORT=6333
      - QDRANT__SERVICE__GRPC_PORT=6334
      - QDRANT__LOG_LEVEL=INFO
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  fastembed:
    image: engrammemory/fastembed:1.0.0
    container_name: engram-fastembed
    restart: unless-stopped
    ports:
      - "11435:8000"
    environment:
      - MODEL_NAME=nomic-ai/nomic-embed-text-v1.5
      - MAX_WORKERS=1
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G

volumes:
  qdrant_storage:
    driver: local
EOF

echo -e "${GREEN}docker-compose.yml created${NC}"

# Start services
echo ""
echo -e "${BLUE}Starting Engram services...${NC}"
echo "This may take a few minutes on first run (downloading models)..."

docker-compose up -d

# Wait for services to be healthy
echo ""
echo -e "${BLUE}Waiting for services to start...${NC}"

wait_for_service() {
    local service=$1
    local url=$2
    local timeout=120
    local count=0

    echo -n "Waiting for $service"
    while ! curl -s "$url" > /dev/null 2>&1; do
        if [ $count -ge $timeout ]; then
            echo -e "\n${RED}Timeout waiting for $service${NC}"
            echo "Check logs with: docker-compose logs $service"
            exit 1
        fi
        echo -n "."
        sleep 2
        ((count+=2))
    done
    echo -e " ${GREEN}OK${NC}"
}

wait_for_service "qdrant" "http://localhost:6333/health"
wait_for_service "fastembed" "http://localhost:11435/health"

# Test the embedding API
echo ""
echo -e "${BLUE}Testing embedding generation...${NC}"
test_response=$(curl -s -X POST http://localhost:11435/embeddings \
    -H "Content-Type: application/json" \
    -d '{"texts":["test"]}')

if echo "$test_response" | grep -q "embeddings"; then
    echo -e "${GREEN}FastEmbed API is working${NC}"
else
    echo -e "${RED}FastEmbed API test failed${NC}"
    echo "Response: $test_response"
    exit 1
fi

# Create Qdrant collection with scalar quantization
echo ""
echo -e "${BLUE}Creating Qdrant collection with scalar quantization...${NC}"
collection_response=$(curl -s -X PUT http://localhost:6333/collections/agent-memory \
    -H "Content-Type: application/json" \
    -d '{
        "vectors": {
            "size": 768,
            "distance": "Cosine"
        },
        "optimizers_config": {
            "default_segment_number": 2
        },
        "replication_factor": 1,
        "quantization_config": {
            "scalar": {
                "type": "int8",
                "quantile": 0.99,
                "always_ram": true
            }
        }
    }')

if echo "$collection_response" | grep -q '"result":true'; then
    echo -e "${GREEN}Collection 'agent-memory' created${NC}"
else
    echo -e "${YELLOW}Collection might already exist${NC}"
fi

# Detect network setup
if docker network ls | grep -q "bridge"; then
    QDRANT_URL="http://localhost:6333"
    EMBEDDING_URL="http://localhost:11435"
else
    QDRANT_URL="http://host.docker.internal:6333"
    EMBEDDING_URL="http://host.docker.internal:11435"
fi

# Generate OpenClaw configuration
echo ""
echo -e "${BLUE}Generating OpenClaw configuration...${NC}"

cat > openclaw-memory-config.json << EOF
{
  "plugins": {
    "allow": ["engram"],
    "slots": {
      "memory": "engram"
    },
    "entries": {
      "engram": {
        "enabled": true,
        "config": {
          "qdrantUrl": "$QDRANT_URL",
          "embeddingUrl": "$EMBEDDING_URL",
          "embeddingModel": "nomic-ai/nomic-embed-text-v1.5",
          "collection": "agent-memory",
          "autoRecall": true,
          "autoCapture": true,
          "maxRecallResults": 5,
          "minRecallScore": 0.35,
          "debug": false
        }
      }
    }
  }
}
EOF

# Setup Python environment
SKILL_DIR="$ENGRAM_REPO_DIR"
echo ""
echo -e "${BLUE}Setting up Python environment...${NC}"

# Create venv and install all dependencies
VENV_OK=false
if python3 -m venv "$SKILL_DIR/.venv" 2>/dev/null; then
    if [ -f "$SKILL_DIR/.venv/bin/pip" ]; then
        "$SKILL_DIR/.venv/bin/pip" install -q -r "$SKILL_DIR/requirements.txt" 2>&1 | tail -1
        VENV_OK=true
        echo -e "${GREEN}Python dependencies installed (venv)${NC}"
    fi
fi

if [ "$VENV_OK" = false ]; then
    rm -rf "$SKILL_DIR/.venv" 2>/dev/null
    echo -e "${YELLOW}venv unavailable — installing with pip3${NC}"
    pip3 install --user -q -r "$SKILL_DIR/requirements.txt" 2>&1 | tail -1
    echo -e "${GREEN}Python dependencies installed (user)${NC}"
fi

# Add bin/ to PATH if not already there
ENGRAM_BIN="$SKILL_DIR/bin"
if ! echo "$PATH" | grep -q "$ENGRAM_BIN"; then
    for rcfile in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [ -f "$rcfile" ]; then
            echo "export PATH=\"$ENGRAM_BIN:\$PATH\"" >> "$rcfile"
        fi
    done
    echo -e "${GREEN}Added engram commands to PATH (restart shell or source rc file)${NC}"
fi

# Success message
echo ""
echo -e "${GREEN}Engram setup complete!${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. Add the following to your ~/.openclaw/openclaw.json:"
echo ""
echo -e "${BLUE}$(cat openclaw-memory-config.json)${NC}"
echo ""
echo "2. (Optional) Add memory rules to your agent's system prompt:"
echo "   See docs/SOUL-RULES.md for recommended rules that teach"
echo "   your agent to use memory proactively. Use what fits your style."
echo ""
echo "3. Restart OpenClaw gateway:"
echo "   openclaw gateway restart"
echo ""
echo "4. Test in your agent:"
echo "   memory_store \"I love persistent memory!\" --category preference"
echo "   memory_search \"memory preferences\""
echo "   context_ask \"How does authentication work?\""
echo ""
echo -e "${YELLOW}Context System:${NC}"
echo "   Initialize a project:  engram-context init /path/to/project --template web-app"
echo "   Search context:        engram-context find \"authentication\""
echo "   Ask questions:         engram-ask \"How does the API work?\""
echo ""
echo -e "${YELLOW}Service URLs:${NC}"
echo "   Qdrant Web UI: http://localhost:6333/dashboard"
echo "   FastEmbed API: http://localhost:11435/docs"
echo ""
echo -e "${YELLOW}Management:${NC}"
echo "   Start:   docker-compose up -d"
echo "   Stop:    docker-compose down"
echo "   Logs:    docker-compose logs -f"
echo ""
echo -e "${GREEN}Your agent now has persistent memory and context awareness.${NC}"
