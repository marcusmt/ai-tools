#!/usr/bin/env python3
"""
Indexing script for the RAG system.

Walks the repository, chunks source files, generates
embeddings via Ollama, and stores everything in a local ChromaDB collection.

Usage:
    python index.py              # incremental (skips already-indexed files)
    python index.py --rebuild    # delete and rebuild from scratch
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import sys
import time
from pathlib import Path

import chromadb
import ollama

from config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    EXCLUDE_PATTERNS,
    INCLUDE_GLOBS,
    MAX_CHUNK_CHARS,
    CHUNK_OVERLAP_CHARS,
    OLLAMA_BASE_URL,
    REPO_ROOT,
    BM25_INDEX_PATH,
    EMBEDDING_BATCH_SIZE
)
from chunkers.java_chunker import chunk_java_file
from chunkers.markdown_chunker import chunk_markdown_file


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def _is_excluded(rel_path: str) -> bool:
    for pattern in EXCLUDE_PATTERNS:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def _matches_include(rel_path: str) -> bool:
    for pattern in INCLUDE_GLOBS:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def discover_files(repo_root: Path) -> list[Path]:
    """Walk repo and return all files matching include globs minus excludes."""
    matched: list[Path] = []
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file():
            continue
        rel = str(path.relative_to(repo_root))
        if _is_excluded(rel):
            continue
        if _matches_include(rel):
            matched.append(path)
    return matched


# ---------------------------------------------------------------------------
# Chunking dispatcher
# ---------------------------------------------------------------------------

def chunk_file(file_path: Path) -> list[dict]:
    """Route a file to the appropriate chunker and return enriched chunks."""
    suffix = file_path.suffix.lower()
    rel = str(file_path.relative_to(REPO_ROOT))

    # Determine module name
    parts = rel.split("/")
    module = parts[0] if len(parts) > 1 else "(root)"

    if suffix == ".java":
        raw_chunks = chunk_java_file(file_path, max_chars=MAX_CHUNK_CHARS)
    elif suffix == ".md":
        raw_chunks = chunk_markdown_file(
            file_path, max_chars=MAX_CHUNK_CHARS, overlap_chars=CHUNK_OVERLAP_CHARS
        )
    else:
        # Config / XML / properties / Dockerfile — treat as single chunk
        text = file_path.read_text(encoding="utf-8", errors="replace")
        raw_chunks = [{
            "content": text[:MAX_CHUNK_CHARS * 2],  # generous limit for configs
            "chunk_type": "config",
            "start_line": 1,
            "end_line": text.count("\n") + 1,
        }]

    # Enrich each chunk with metadata
    for chunk in raw_chunks:
        chunk["file_path"] = rel
        chunk["module"] = module
        chunk["language"] = _language_for_suffix(suffix)

    return raw_chunks


def _language_for_suffix(suffix: str) -> str:
    return {
        ".java": "java",
        ".md": "markdown",
        ".xml": "xml",
        ".properties": "properties",
        ".yml": "yaml",
        ".yaml": "yaml",
    }.get(suffix, "text")


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

_client = ollama.Client(host=OLLAMA_BASE_URL)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using Ollama."""
    results: list[list[float]] = []
    # Ollama's embed endpoint accepts a list directly
    response = _client.embed(model=EMBEDDING_MODEL, input=texts)
    return response.embeddings


# ---------------------------------------------------------------------------
# Main indexing logic
# ---------------------------------------------------------------------------

def build_index(rebuild: bool = False) -> None:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    db = chromadb.PersistentClient(path=str(CHROMA_DIR))

    if rebuild:
        try:
            db.delete_collection(COLLECTION_NAME)
            print("🗑️  Deleted existing Chroma collection.")
        except Exception:
            pass

    collection = db.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    existing_ids = set(collection.get()["ids"]) if not rebuild else set()

    files = discover_files(REPO_ROOT)
    print(f"📂 Found {len(files)} files to index.")

    total_chunks = 0
    skipped = 0
    batch_ids: list[str] = []
    batch_docs: list[str] = []
    batch_metas: list[dict] = []
    batch_size = EMBEDDING_BATCH_SIZE  # embed in batches for efficiency

    # For BM25 keyword index
    all_chunks_for_bm25 = []
    
    for file_path in files:
        chunks = chunk_file(file_path)
        for chunk in chunks:
            # Deterministic ID based on file + line range
            chunk_id = hashlib.sha256(
                f"{chunk['file_path']}:{chunk['start_line']}-{chunk['end_line']}:{chunk['chunk_type']}".encode()
            ).hexdigest()[:20]

            metadata = {
                "file_path": chunk["file_path"],
                "module": chunk["module"],
                "language": chunk["language"],
                "chunk_type": chunk["chunk_type"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
            }
            
            # Keep all chunks for BM25 (it needs to rebuild entirely if we update BM25)
            all_chunks_for_bm25.append({
                "id": chunk_id,
                "content": chunk["content"],
                "metadata": metadata
            })

            if chunk_id in existing_ids:
                skipped += 1
                continue

            batch_ids.append(chunk_id)
            batch_docs.append(chunk["content"])
            batch_metas.append(metadata)
            total_chunks += 1

            if len(batch_ids) >= batch_size:
                _flush_batch(collection, batch_ids, batch_docs, batch_metas)
                batch_ids, batch_docs, batch_metas = [], [], []

    # Flush remaining vectors
    if batch_ids:
        _flush_batch(collection, batch_ids, batch_docs, batch_metas)
        
    # Build and save BM25 Index
    print(f"⏳ Building new BM25 Keyword index over {len(all_chunks_for_bm25)} chunks...")
    _build_and_save_bm25(all_chunks_for_bm25)

    print(f"\n✅ Indexed {total_chunks} new chunks into Chroma ({skipped} skipped, already present).")
    print(f"   Collection total: {collection.count()} chunks.")
    print(f"   BM25 Index rebuilt and saved.")


def _build_and_save_bm25(chunks: list[dict]):
    """Tokenize and build a BM25 index, then pickle it to disk."""
    import pickle
    from rank_bm25 import BM25Okapi
    
    # Simple whitespace/punctuation tokenizer for code & text
    import re
    def tokenize(text: str) -> list[str]:
        # Lowercase and split on non-alphanumeric
        return [t for t in re.split(r'[^a-zA-Z0-9]+', text.lower()) if t]
        
    tokenized_corpus = [tokenize(c["content"]) for c in chunks]
    bm25 = BM25Okapi(tokenized_corpus)
    
    # Save the index and the chunk metadata dictionary it aligns with
    from config import BM25_INDEX_PATH
    with open(BM25_INDEX_PATH, "wb") as f:
        pickle.dump({
            "bm25": bm25,
            "chunks": chunks
        }, f)


def _flush_batch(
    collection,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
) -> None:
    print(f"   ⏳ Embedding batch of {len(ids)} chunks…", end="", flush=True)
    t0 = time.time()
    embeddings = embed_texts(documents)
    elapsed = time.time() - t0
    print(f" done ({elapsed:.1f}s)")

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=documents,
        metadatas=metadatas,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Index the codebase for RAG.")
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Delete the existing index and rebuild from scratch.",
    )
    args = parser.parse_args()

    from config import BM25_INDEX_PATH
    print("🔍 RAG Indexer (Hybrid Vector + Keyword)")
    print(f"   Repo root : {REPO_ROOT}")
    print(f"   ChromaDB  : {CHROMA_DIR}")
    print(f"   BM25 idx  : {BM25_INDEX_PATH}")
    print(f"   Embed mod : {EMBEDDING_MODEL}")
    print()

    build_index(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
