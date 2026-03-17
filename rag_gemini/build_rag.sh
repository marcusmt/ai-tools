#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "=========================================================="
echo "🚀 RAG System - Automated Build & Setup"
echo "=========================================================="

# Ensure we are in the rag directory
cd "$(dirname "$0")"

# 1. Read required models from config.py using Python
# This ensures that pulling is always synced with config.py
echo "🔍 Extracting required models from config.py..."
EMBED_MODEL=$(python3 -c "import config; print(config.EMBEDDING_MODEL)")
LLM_MODEL=$(python3 -c "import config; print(config.DEFAULT_LLM_MODEL)")

echo "   - Embedding Model: $EMBED_MODEL"
echo "   - Chat LLM Model:  $LLM_MODEL"

# 2. Pull models via Ollama
echo ""
echo "📥 Pulling models from Ollama (this may take a while if not cached)..."
ollama pull "$EMBED_MODEL"
ollama pull "$LLM_MODEL"

# 3. Setup Python Virtual Environment
echo ""
echo "🐍 Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Determine correct activation script based on shell
if [[ "$SHELL" == *"fish"* ]]; then
    source .venv/bin/activate.fish
else
    source .venv/bin/activate
fi

# 4. Install dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 5. Build the Vector and BM25 Indexes
echo ""
echo "🏗️  Building the codebase indices (Vector + BM25)..."
python index.py --rebuild

echo ""
echo "=========================================================="
echo "✅ Build Complete!"
echo "Starting RAG server on the default config port..."
echo "To override the port manually, you can run:"
echo "  source .venv/bin/activate && python server.py --port 8080"
echo "=========================================================="

source .venv/bin/activate
python server.py