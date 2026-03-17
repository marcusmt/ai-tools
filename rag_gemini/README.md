# Local RAG — Java Codebase Q&A

A fully local RAG system that indexes a Java codebase and lets local LLMs answer questions about it with precise source-code context.

## Prerequisites

| Tool             | Install                                          |
| ---------------- | ------------------------------------------------ |
| **Python 3.10+** | System package manager                           |
| **Ollama**       | `curl -fsSL https://ollama.com/install.sh \| sh` |

## Quick Start

You do **not** need to memorize commands. Everything is centralized.

### 1. Configure your Models

Open `rag/config.py` to change embedding models, chunk sizes, or LLMs.
By default, it is configured for maximum possible accuracy using `mxbai-embed-large` and `qwen2.5-coder:14b` (which fits comfortably in < 32GB RAM).

### 2. Build & Setup

Run the automated build script. It will automatically read your `config.py`, pull the required models via Ollama, create a virtual environment, install dependencies, and build the ChromaDB index.
It will start the server at the end. Or start it manually, if you want.

```bash
cd rag/
./build_rag.sh
```

### 3. Start the Server

Once the index is built, start the FastAPI server:

```bash
cd rag/
source .venv/bin/activate
python server.py --port 8080
```

By default, the server starts at **http://localhost:8000** (this can be changed globally in `config.py` or overridden via the `--port` flag).

## Endpoints

| Endpoint               | Method | Description                                |
| ---------------------- | ------ | ------------------------------------------ |
| `/health`              | GET    | Liveness check, returns collection size    |
| `/query`               | POST   | Retrieve relevant code chunks              |
| `/v1/chat/completions` | POST   | OpenAI-compatible proxy with automatic RAG |

## Usage Examples

### Direct retrieval

```bash
curl http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How does the application authenticate with the database?", "top_k": 5}'
```

### Chat with RAG context (OpenAI-compatible)

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-coder:14b",
    "messages": [{"role": "user", "content": "How does the main authentication logic work?"}]
  }'
```

### Use with LLM UIs

Point any OpenAI-compatible client at `http://localhost:8000/v1`:

- **Open WebUI** — set the API base URL
- **Continue (VS Code)** — configure as an OpenAI provider
- **Aider** — `aider --openai-api-base http://localhost:8000/v1`

## Re-indexing

```bash
# Incremental (only new/changed files)
python index.py

# Full rebuild
python index.py --rebuild
```

## Architecture

```
User question
    ↓
[RAG Server]  →  embed question  →  query ChromaDB  →  top-k chunks
    ↓
inject chunks into system prompt
    ↓
forward to Ollama (qwen2.5-coder:14b)
    ↓
stream response back
```

## Automated Evaluation & Tuning

To ensure maximum accuracy, you can run the automated "LLM-as-a-Judge" pipeline. This script scans the codebase, generates difficult questions, asks the live RAG server, and scientifically grades the responses out of 5.

```bash
cd rag/
# Make sure server.py is running in another terminal!
./evaluate_rag.sh
```

This will automatically pull the required judge model (configured in `config.py`) and evaluate 20 questions.
To evaluate more questions, pass the number as an argument:

```bash
./evaluate_rag.sh 50
```

The results are saved to `rag/evaluate/eval_results.json` so you can inspect where the RAG struggles.

## File Structure

```
rag/
├── README.md           ← this file
├── requirements.txt    ← Python deps (includes rank_bm25, sentence-transformers)
├── config.py           ← **Master Configuration File** (models, paths, sizes)
├── build_rag.sh        ← 1-click build (Reads config > Pulls models > Indexes)
├── evaluate_rag.sh     ← 1-click test (Generates QA > Grades locally)
├── index.py            ← backend indexing logic
├── server.py           ← backend FastAPI server
├── chunkers/
│   ├── java_chunker.py     ← tree-sitter Java splitter
│   └── markdown_chunker.py ← header-aware Markdown splitter
├── evaluate/
│   └── evaluator.py        ← automated LLM-as-a-Judge script
├── chroma_data/        ← (gitignored) vector DB storage
└── bm25_index.pkl      ← (gitignored) keyword search index
```
