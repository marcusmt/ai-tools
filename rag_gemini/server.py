#!/usr/bin/env python3
"""
RAG query server for the codebase.

Endpoints:
  GET  /health                  — liveness check
  POST /query                   — retrieve relevant chunks for a question
  POST /v1/chat/completions     — OpenAI-compatible proxy with automatic RAG
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import chromadb
import httpx
import ollama
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse

from config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    DEFAULT_LLM_MODEL,
    DEFAULT_TOP_K,
    EMBEDDING_MODEL,
    OLLAMA_BASE_URL,
    SYSTEM_PROMPT_TEMPLATE,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="RAG Server", version="1.0.0")

_db: chromadb.PersistentClient | None = None
_collection = None
_ollama: ollama.Client | None = None
_bm25_data = None
_reranker = None


def _get_collection():
    global _db, _collection
    if _collection is None:
        _db = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _db.get_collection(name=COLLECTION_NAME)
    return _collection


def _get_ollama():
    global _ollama
    if _ollama is None:
        _ollama = ollama.Client(host=OLLAMA_BASE_URL)
    return _ollama


def _get_bm25():
    """Load BM25 index from disk."""
    global _bm25_data
    from config import BM25_INDEX_PATH
    import pickle
    if _bm25_data is None:
        if not BM25_INDEX_PATH.exists():
            print(f"⚠️ BM25 index not found at {BM25_INDEX_PATH}")
            return None
        with open(BM25_INDEX_PATH, "rb") as f:
            _bm25_data = pickle.load(f)
    return _bm25_data


def _get_reranker():
    """Load CrossEncoder model lazily."""
    global _reranker
    from config import RERANKER_MODEL
    from sentence_transformers import CrossEncoder
    if _reranker is None:
        print(f"⏳ Loading re-ranker model ({RERANKER_MODEL})...")
        _reranker = CrossEncoder(RERANKER_MODEL, max_length=512)
    return _reranker

import re
def tokenize(text: str) -> list[str]:
    return [t for t in re.split(r'[^a-zA-Z0-9]+', text.lower()) if t]


# ---------------------------------------------------------------------------
# Retrieval helper (Hybrid + Reranking)
# ---------------------------------------------------------------------------

def retrieve(question: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """
    1. Retrieve `INITIAL_RETRIEVAL_K` chunks via Vector Search.
    2. Retrieve `INITIAL_RETRIEVAL_K` chunks via BM25 Keyword Search.
    3. Merge using Reciprocal Rank Fusion (RRF).
    4. Re-rank top candidates using Cross-Encoder.
    5. Return final `top_k`.
    """
    from config import INITIAL_RETRIEVAL_K
    
    # 1. Vector Search
    client = _get_ollama()
    collection = _get_collection()
    response = client.embed(model=EMBEDDING_MODEL, input=[question])
    q_embedding = response.embeddings[0]

    v_results = collection.query(
        query_embeddings=[q_embedding],
        n_results=INITIAL_RETRIEVAL_K,
        include=["documents", "metadatas", "distances"],
    )

    vector_chunks = {}
    for i in range(len(v_results["ids"][0])):
        c_id = v_results["ids"][0][i]
        vector_chunks[c_id] = {
            "id": c_id,
            "content": v_results["documents"][0][i],
            "metadata": v_results["metadatas"][0][i],
            "vector_rank": i
        }

    # 2. BM25 Keyword Search
    bm25_data = _get_bm25()
    keyword_chunks = {}
    if bm25_data:
        tokenized_q = tokenize(question)
        bm25 = bm25_data["bm25"]
        all_chunks = bm25_data["chunks"]
        
        # Get scores
        scores = bm25.get_scores(tokenized_q)
        # Sort by score descending
        import numpy as np
        top_n_idx = np.argsort(scores)[::-1][:INITIAL_RETRIEVAL_K]
        
        for rank, idx in enumerate(top_n_idx):
            if scores[idx] > 0:  # Only if there's an actual keyword match
                chunk = all_chunks[idx]
                c_id = chunk["id"]
                keyword_chunks[c_id] = {
                    "id": c_id,
                    "content": chunk["content"],
                    "metadata": chunk["metadata"],
                    "keyword_rank": rank
                }

    # 3. Reciprocal Rank Fusion (RRF)
    # Combine results from both retrievers
    all_candidates = {}
    for c_id, data in vector_chunks.items():
        all_candidates[c_id] = data
    for c_id, data in keyword_chunks.items():
        if c_id not in all_candidates:
            all_candidates[c_id] = data
        else:
            all_candidates[c_id]["keyword_rank"] = data["keyword_rank"]

    # Calculate RRF score for each candidate. RRF_score = 1 / (k + rank)
    from config import RRF_K_CONSTANT
    for c_id, data in all_candidates.items():
        v_rank = data.get("vector_rank", 1000)
        k_rank = data.get("keyword_rank", 1000)
        data["rrf_score"] = (1.0 / (RRF_K_CONSTANT + v_rank)) + (1.0 / (RRF_K_CONSTANT + k_rank))

    # Sort candidates by combined RRF score and take top INITIAL_RETRIEVAL_K
    sorted_candidates = sorted(all_candidates.values(), key=lambda x: x["rrf_score"], reverse=True)
    top_candidates = sorted_candidates[:INITIAL_RETRIEVAL_K]

    # 4. Cross-Encoder Re-ranking
    reranker = _get_reranker()
    # Format input for cross-encoder: pairs of (query, chunk_text)
    pairs = [[question, c["content"]] for c in top_candidates]
    if pairs:
        rerank_scores = reranker.predict(pairs)
        for i, score in enumerate(rerank_scores):
            top_candidates[i]["rerank_score"] = float(score)

        # Sort by final reranker score
        final_sorted = sorted(top_candidates, key=lambda x: x.get("rerank_score", -999), reverse=True)
    else:
        final_sorted = top_candidates

    # 5. Return top_k
    return final_sorted[:top_k]


def _format_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a context block for the LLM prompt."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        header = f"[{i}] {meta['file_path']}  (L{meta['start_line']}–{meta['end_line']}, {meta['chunk_type']})"
        parts.append(f"{header}\n```{meta['language']}\n{chunk['content']}\n```")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    collection = _get_collection()
    return {"status": "ok", "collection_size": collection.count()}


@app.post("/query")
async def query_endpoint(request: Request):
    body = await request.json()
    question = body.get("question", "")
    top_k = body.get("top_k", DEFAULT_TOP_K)

    if not question:
        return JSONResponse(status_code=400, content={"error": "question is required"})

    chunks = retrieve(question, top_k=top_k)
    return {
        "question": question,
        "results": chunks,
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completions proxy.
    Retrieves relevant context, injects it as a system message, then forwards
    the request to Ollama and streams the response back.
    """
    body = await request.json()
    messages: list[dict] = body.get("messages", [])
    model = body.get("model", DEFAULT_LLM_MODEL)
    stream = body.get("stream", False)

    # Extract the user's question (last user message)
    user_question = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_question = msg.get("content", "")
            break

    # Retrieve context
    chunks = retrieve(user_question) if user_question else []
    context = _format_context(chunks)

    # Build augmented messages — prepend system context
    augmented_messages = [
        {"role": "system", "content": SYSTEM_PROMPT_TEMPLATE.format(context=context)},
    ] + messages

    client = _get_ollama()

    if stream:
        return StreamingResponse(
            _stream_ollama(client, model, augmented_messages),
            media_type="text/event-stream",
        )
    else:
        response = client.chat(model=model, messages=augmented_messages, stream=False)
        # Convert to OpenAI-compatible format
        return _to_openai_response(response, model)


async def _stream_ollama(
    client: ollama.Client,
    model: str,
    messages: list[dict],
) -> AsyncIterator[str]:
    """Stream Ollama chat response in OpenAI SSE format."""
    stream = client.chat(model=model, messages=messages, stream=True)
    chunk_id = f"chatcmpl-{int(time.time())}"

    for chunk in stream:
        delta_content = chunk.message.content
        sse_data = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": delta_content},
                "finish_reason": None,
            }],
        }
        yield f"data: {json.dumps(sse_data)}\n\n"

    # Send the final [DONE] marker
    yield "data: [DONE]\n\n"


def _to_openai_response(ollama_response, model: str) -> dict:
    """Convert an Ollama chat response to OpenAI format."""
    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": ollama_response.message.content,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": ollama_response.prompt_eval_count or 0,
            "completion_tokens": ollama_response.eval_count or 0,
            "total_tokens": (ollama_response.prompt_eval_count or 0)
                + (ollama_response.eval_count or 0),
        },
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    import argparse
    from config import SERVER_PORT

    parser = argparse.ArgumentParser(description="RAG API Server")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help="Port to run the server on")
    args = parser.parse_args()

    print(f"🚀 Starting RAG Server on http://localhost:{args.port}")
    print(f"   ChromaDB: {CHROMA_DIR}")
    print(f"   Ollama:   {OLLAMA_BASE_URL}")
    print(f"   LLM:      {DEFAULT_LLM_MODEL}")
    print()
    uvicorn.run(app, host="0.0.0.0", port=args.port)
