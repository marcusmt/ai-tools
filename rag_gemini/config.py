"""
Central configuration for the RAG system.
All paths, model names, and tunables live here.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Repo root (parent of this rag/ directory)
REPO_ROOT = Path(__file__).resolve().parent.parent

# Persistent ChromaDB storage
CHROMA_DIR = Path(__file__).resolve().parent / "chroma_data"

# ChromaDB collection name
COLLECTION_NAME = "java_codebase"

# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = "http://localhost:11434"

# Embedding model served by Ollama — mxbai-embed-large for highest accuracy
EMBEDDING_MODEL = "mxbai-embed-large"

# How many chunks to process at once when building the index.
# Reduce to 16 or 8 if embedding large files causes out-of-memory errors.
EMBEDDING_BATCH_SIZE = 32

# Default LLM model for the chat proxy — accuracy-first choice that fits in < 32GB RAM
# qwen3-coder - answers ranked > 2
# deepseek-coder-v2 - answers ranked > 1 to < 5
# qwen2.5-coder:14b - answers ranked 1 to < 4 - maybe couple of 5
DEFAULT_LLM_MODEL = "qwen3-coder"

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
# Maximum chunk size in characters (not tokens — ~4 chars ≈ 1 token)
MAX_CHUNK_CHARS = 4000

# Overlap between consecutive text chunks (for non-AST splitting)
CHUNK_OVERLAP_CHARS = 200

# ---------------------------------------------------------------------------
# Retrieval & Re-ranking
# ---------------------------------------------------------------------------
# Cross-encoder re-ranker model for maximum accuracy (runs locally via sentence-transformers)
RERANKER_MODEL = "BAAI/bge-reranker-large"

# How many chunks to retrieve initially (combination of BM25 + Vector)
INITIAL_RETRIEVAL_K = 60

# Constant used in Reciprocal Rank Fusion (RRF) to blend keyword and vector scores.
# The standard value is typically 60.
RRF_K_CONSTANT = 60

# How many chunks to keep after strict cross-encoder re-ranking
DEFAULT_TOP_K = 20

# Path to save the BM25 keyword index
BM25_INDEX_PATH = Path(__file__).resolve().parent / "bm25_index.pkl"

# ---------------------------------------------------------------------------
# Server Settings
# ---------------------------------------------------------------------------
SERVER_PORT = 8000

# ---------------------------------------------------------------------------
# Indexing — file selection globs (relative to REPO_ROOT)
# ---------------------------------------------------------------------------
INCLUDE_GLOBS = [
    "**/*.java",
    "**/*.md",
    "**/pom.xml",
    "**/*.properties",
    "**/*.yml",
    "**/*.yaml",
    "**/*.xml",
    "docker/Dockerfile*",
    "jenkins/**",
]

EXCLUDE_PATTERNS = [
    "**/target/**",
    "**/test/**",
    "**/.git/**",
    "rag/**",
    "**/node_modules/**",
]

# ---------------------------------------------------------------------------
# System prompt injected when using the /v1/chat/completions proxy
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_TEMPLATE = """You are an expert assistant for a Java codebase.
You will be provided with source code chunks. Your goal is to answer developer questions accurately.

Use the following retrieved code and documentation excerpts to answer the user's question.
If you don't find enough information in the excerpts, say so — do not hallucinate.

---
{context}
---
"""
