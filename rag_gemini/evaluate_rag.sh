#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

echo "=========================================================="
echo "⚖️  RAG System - Automated Evaluation Planner"
echo "=========================================================="

# Ensure we are in the rag directory
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "❌ Error: Virtual environment (.venv) not found. Please run ./build_rag.sh first."
    exit 1
fi

# Determine correct activation script based on shell
if [[ "$SHELL" == *"fish"* ]]; then
    source .venv/bin/activate.fish
else
    source .venv/bin/activate
fi

# Read the RAG Model from Config
RAG_MODEL=$(python3 -c "import config; print(config.DEFAULT_LLM_MODEL)")

# The Judge Model (defaults to the 72B model for absolute maximum critical scoring)
# We read this directly from the evaluator's default variables
JUDGE_MODEL=$(python3 -c "import sys; sys.path.append('evaluate'); import evaluator; print(evaluator.DEFAULT_JUDGE)")

NUM_QUESTIONS=${1:-20}  # Accepts an argument for number of questions, defaults to 20

echo "🔍 Evaluation Setup:"
echo "   - Number of Questions to generate: $NUM_QUESTIONS"
echo "   - Generator/Judge Model:           $JUDGE_MODEL"
echo "   - RAG Answering Model:             $RAG_MODEL"
echo ""

# Ensure the Judge model is pulled
echo "📥 Ensuring the Judge model ($JUDGE_MODEL) is available locally..."
ollama pull "$JUDGE_MODEL"

echo ""
echo "⏳ Warning: The RAG server (server.py) must be running in a separate terminal."
echo "Press [ENTER] to continue if the server is already running, or [CTRL+C] to cancel."
read dummy

echo ""
echo "🚀 Starting Evaluation Pipeline..."

python evaluate/evaluator.py \
    --num-qs "$NUM_QUESTIONS" \
    --judge "$JUDGE_MODEL" \
    --rag-model "$RAG_MODEL"

echo "=========================================================="
echo "✅ Evaluation Complete! See rag/evaluate/eval_results.json"
echo "=========================================================="
