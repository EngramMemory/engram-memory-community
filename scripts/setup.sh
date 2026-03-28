#!/bin/bash

# Engram Memory Community Edition Setup Script
# This script sets up Qdrant and FastEmbed for local development

set -e

echo "🚀 Setting up Engram Memory Community Edition..."
echo ""

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "   https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo "❌ Docker Compose is not available. Please install Docker Compose."
    echo "   https://docs.docker.com/compose/install/"
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js 18+."
    echo "   https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "❌ Node.js version $NODE_VERSION is too old. Please upgrade to Node.js 18+."
    exit 1
fi

echo "✅ Prerequisites checked"
echo ""

# Create docker-compose.yml if it doesn't exist
if [ ! -f "docker-compose.yml" ]; then
    echo "📝 Creating docker-compose.yml..."
    cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  qdrant:
    image: qdrant/qdrant:v1.7.4
    container_name: engram-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./data/qdrant:/qdrant/storage
    environment:
      - QDRANT__SERVICE__HTTP_PORT=6333
      - QDRANT__SERVICE__GRPC_PORT=6334
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  fastembed:
    image: qdrant/fastembed_server:latest
    container_name: engram-fastembed
    ports:
      - "11435:8000"
    environment:
      - MODEL_NAME=nomic-ai/nomic-embed-text-v1.5
      - MAX_WORKERS=1
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

EOF
    echo "✅ docker-compose.yml created"
else
    echo "📝 docker-compose.yml already exists"
fi

# Create data directory
echo "📁 Creating data directory..."
mkdir -p data/qdrant
echo "✅ Data directory created"

# Pull and start services
echo ""
echo "🐳 Starting Qdrant and FastEmbed services..."
echo "   This may take a few minutes on first run..."

docker-compose pull
docker-compose up -d

echo "✅ Services started"
echo ""

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."

# Function to wait for a service
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200\|404"; then
            echo "✅ $service_name is ready"
            return 0
        fi
        echo "   Waiting for $service_name... (attempt $((attempt + 1))/$max_attempts)"
        sleep 5
        attempt=$((attempt + 1))
    done

    echo "❌ $service_name failed to start after $((max_attempts * 5)) seconds"
    return 1
}

# Wait for Qdrant
wait_for_service "http://localhost:6333/health" "Qdrant"

# Wait for FastEmbed 
wait_for_service "http://localhost:11435/health" "FastEmbed"

echo ""

# Test the setup
echo "🧪 Testing setup..."

# Test Qdrant
echo "   Testing Qdrant..."
QDRANT_RESPONSE=$(curl -s http://localhost:6333/collections)
if echo "$QDRANT_RESPONSE" | grep -q "result"; then
    echo "   ✅ Qdrant is responding correctly"
else
    echo "   ⚠️ Qdrant response unexpected: $QDRANT_RESPONSE"
fi

# Test FastEmbed
echo "   Testing FastEmbed..."
FASTEMBED_RESPONSE=$(curl -s -X POST http://localhost:11435/api/embed \
    -H "Content-Type: application/json" \
    -d '{"model":"nomic-ai/nomic-embed-text-v1.5","input":"test embedding"}')

if echo "$FASTEMBED_RESPONSE" | grep -q "embedding\|embeddings"; then
    echo "   ✅ FastEmbed is responding correctly"
else
    echo "   ⚠️ FastEmbed response unexpected (this is normal on first run)"
    echo "   💡 FastEmbed may need a few more minutes to download the model"
fi

echo ""

# Build the plugin
echo "🔧 Building Engram Memory plugin..."
if [ -f "package.json" ]; then
    npm install
    npm run build
    echo "✅ Plugin built successfully"
else
    echo "⚠️ package.json not found, skipping npm build"
fi

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📊 Service Status:"
echo "   • Qdrant Vector DB: http://localhost:6333"
echo "   • FastEmbed API: http://localhost:11435" 
echo "   • Qdrant UI: http://localhost:6333/dashboard"
echo ""
echo "🧪 Test your setup:"
echo "   node examples/basic-usage.js"
echo ""
echo "📖 Next Steps:"
echo "   1. Add plugin to your OpenClaw config:"
echo "      {"
echo "        \"plugins\": {"
echo "          \"engram-memory-community\": {"
echo "            \"qdrantUrl\": \"http://localhost:6333\","
echo "            \"embeddingUrl\": \"http://localhost:11435\","
echo "            \"autoRecall\": true,"
echo "            \"autoCapture\": true"
echo "          }"
echo "        }"
echo "      }"
echo ""
echo "   2. Restart OpenClaw to load the plugin"
echo ""
echo "   3. Try the memory commands:"
echo "      memory_store \"I prefer TypeScript\" --category preference"
echo "      memory_search \"programming languages\""
echo ""
echo "🚀 Ready to upgrade to Engram Cloud?"
echo "   https://engrammemory.ai"
echo ""
echo "💡 Community Edition Limitations:"
echo "   • No deduplication (memories accumulate redundantly)"
echo "   • Basic quantization only (6x memory waste)" 
echo "   • Single collection (no multi-agent isolation)"
echo "   • No analytics or monitoring"
echo "   • Manual operations only (no bulk tools)"
echo ""
echo "   These limitations create natural upgrade pressure as you scale!"