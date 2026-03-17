#!/usr/bin/env python3
"""
Evaluation Runner for RAG System.

1. Generates ground-truth Q&A from random code chunks using a strong LLM.
2. Runs the questions through the RAG system to get retrieved answers.
3. Uses the strong LLM (LLM-as-a-Judge) to score the RAG answers.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from tqdm import tqdm

import ollama
import chromadb

# To import from parent folder
import sys
sys.path.append(str(Path(__file__).parent.parent))

from config import CHROMA_DIR, COLLECTION_NAME, OLLAMA_BASE_URL, DEFAULT_LLM_MODEL
from chunkers.java_chunker import chunk_java_file
from index import discover_files, chunk_file, REPO_ROOT

# The Judge model — requires high reasoning capability
JUDGE_MODEL = DEFAULT_LLM_MODEL
# To test quickly, we use the default LLM model by default, but you can override it
DEFAULT_JUDGE = DEFAULT_LLM_MODEL


PROMPT_GENERATE_QA = """You are a senior Java architect. 
I am going to provide you with a chunk of source code from a Java project.
Your task is to write ONE highly specific, non-trivial question about this code that a new developer might ask, along with the correct answer.

The question must be self-contained (do not say "in this snippet") and should focus on architecture, business logic, or control flow.
The answer must be accurate based ONLY on the provided code.

Format your response EXACTLY as a JSON object:
{{
  "question": "<your question>",
  "answer": "<your correct answer>"
}}

Code snippet:
{code}
"""


PROMPT_JUDGE = """You are an impartial expert judge grading an AI assistant's answer to a developer's question about a codebase.

You will be given:
1. The Question
2. The True Answer (Ground Truth)
3. The AI Assistant's Answer (which was generated using Retrieval-Augmented Generation)

Your task is to grade the AI Assistant's Answer against the True Answer on a scale of 1 to 5.
- 5: Perfect match in facts and details.
- 4: Correct, but missing a very minor detail.
- 3: Partially correct, but missing important context or containing slight inaccuracies.
- 2: Mostly incorrect or hallucinated, with only a small kernel of truth.
- 1: Completely wrong, contradictory, or failed to answer.

You must output EXACTLY a JSON object in this format:
{{
  "score": <int 1-5>,
  "reasoning": "<1-2 sentence explanation of the score>"
}}

Question: {question}

True Answer: {true_answer}

AI Assistant's Answer: {rag_answer}
"""


def get_random_chunks(num_chunks: int = 20) -> list[str]:
    """Extract random chunks from the DB or by chunking random files."""
    try:
        db = chromadb.PersistentClient(path=str(CHROMA_DIR))
        collection = db.get_collection(name=COLLECTION_NAME)
        all_docs = collection.get()
        if not all_docs or not all_docs["documents"]:
            raise ValueError("Chroma DB is empty")
        
        docs = all_docs["documents"]
        # Filter for moderately sized chunks (avoid tiny fragments or huge configs)
        valid_docs = [d for d in docs if 500 < len(d) < 3000]
        if not valid_docs:
            valid_docs = docs
            
        return random.sample(valid_docs, min(num_chunks, len(valid_docs)))
    except Exception as e:
        print(f"Fallback to file parsing due to DB error: {e}")
        files = discover_files(REPO_ROOT)
        java_files = [f for f in files if f.suffix == ".java"]
        chunks = []
        for f in random.sample(java_files, min(100, len(java_files))):
            file_chunks = chunk_file(f)
            chunks.extend([c["content"] for c in file_chunks if 500 < len(c["content"]) < 3000])
        return random.sample(chunks, min(num_chunks, len(chunks)))


import re

def _extract_json(text: str) -> dict:
    """Extract and parse a JSON object from a string that might contain markdown or other text."""
    # Try to find JSON inside markdown blocks first
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
            
    # Fallback to finding the first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
            
    # Absolute fallback
    return json.loads(text)

def generate_ground_truth(chunks: list[str], model: str) -> list[dict]:
    print(f"\n🧠 Generating {len(chunks)} Ground Truth Q&A pairs using {model}...")
    client = ollama.Client(host=OLLAMA_BASE_URL)
    dataset = []
    
    for chunk in tqdm(chunks, desc="Generating QA"):
        for attempt in range(3):
            try:
                prompt = PROMPT_GENERATE_QA.format(code=chunk)
                response = client.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    format="json"
                )
                result = _extract_json(response.message.content)
                if "question" in result and "answer" in result:
                    dataset.append({
                        "question": result["question"],
                        "true_answer": result["answer"],
                        "source_chunk": chunk
                    })
                    break
            except Exception as e:
                if attempt == 2:
                    print(f"  [Skipped] Failed to generate valid JSON: {e}")
            
    return dataset


def run_rag_answers(dataset: list[dict], rag_model: str) -> list[dict]:
    """Use the actual local server.py to get answers."""
    print(f"\n🤖 Getting RAG answers via local server using {rag_model}...")
    import requests
    
    for item in tqdm(dataset, desc="Querying RAG"):
        try:
            # First, fetch context via our newly upgraded Hybrid Retriever
            r_retrieval = requests.post("http://localhost:8000/query", json={
                "question": item["question"],
                "top_k": 10
            })
            r_retrieval.raise_for_status()
            
            # Now run the chat proxy
            r_chat = requests.post("http://localhost:8000/v1/chat/completions", json={
                "model": rag_model,
                "messages": [{"role": "user", "content": item["question"]}]
            })
            r_chat.raise_for_status()
            
            chat_data = r_chat.json()
            item["rag_answer"] = chat_data["choices"][0]["message"]["content"]
            
        except Exception as e:
            print(f"Failed RAG query: {e}")
            item["rag_answer"] = "ERROR: Failed to retrieve answer"
            
    return dataset


def judge_answers(dataset: list[dict], judge_model: str) -> list[dict]:
    print(f"\n⚖️ Judging answers using {judge_model}...")
    client = ollama.Client(host=OLLAMA_BASE_URL)
    
    total_score = 0
    valid_scores = 0
    
    for item in tqdm(dataset, desc="Judging"):
        if item.get("rag_answer", "").startswith("ERROR"):
            item["score"] = 0
            item["reasoning"] = "RAG failure"
            continue
            
        for attempt in range(3):
            try:
                prompt = PROMPT_JUDGE.format(
                    question=item["question"],
                    true_answer=item["true_answer"],
                    rag_answer=item["rag_answer"]
                )
                response = client.chat(
                    model=judge_model,
                    messages=[{"role": "user", "content": prompt}],
                    format="json"
                )
                result = _extract_json(response.message.content)
                score = result.get("score", 1)
                
                item["score"] = score
                item["reasoning"] = result.get("reasoning", "")
                
                total_score += score
                valid_scores += 1
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  [Failed] Could not judge item: {e}")
                    item["score"] = 0
            
    if valid_scores > 0:
        avg = total_score / valid_scores
        print(f"\n===============")
        print(f"🏆 Final RAG Accuracy Score: {avg:.2f} / 5.0")
        print(f"===============")
        
    return dataset


def main():
    parser = argparse.ArgumentParser(description="Evaluate the RAG system.")
    parser.add_argument("--num-qs", type=int, default=10, help="Number of questions to generate")
    parser.add_argument("--judge", type=str, default=DEFAULT_JUDGE, help="LLM to use for generation & judging")
    parser.add_argument("--rag-model", type=str, default=DEFAULT_LLM_MODEL, help="LLM used by RAG server")
    parser.add_argument("--output", type=str, default="eval_results.json", help="Output JSON file")
    
    args = parser.parse_args()
    
    print(f"Starting Evaluation Pipeline ({args.num_qs} questions)")
    
    chunks = get_random_chunks(args.num_qs)
    dataset = generate_ground_truth(chunks, args.judge)
    
    if not dataset:
        print("Failed to generate any valid Q&A pairs. Exiting.")
        return
        
    dataset = run_rag_answers(dataset, args.rag_model)
    dataset = judge_answers(dataset, args.judge)
    
    out_path = Path(__file__).parent / args.output
    out_path.write_text(json.dumps(dataset, indent=2))
    print(f"\n💾 Saved full evaluation results to {out_path}")


if __name__ == "__main__":
    main()
