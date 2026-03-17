#!/usr/bin/env python3
"""
Smart Router for Local-to-Cloud LLM Escalation.
CLI-based version using @google/gemini-cli.

1. Takes a user question.
2. Retrieves context chunks from the local RAG database.
3. Asks the local LLM if it can confidently answer the question.
4. If local model answers successfully, returns the local answer.
5. If local model outputs "ESCALATE", sends the context and question to Gemini CLI.
"""

import argparse
import os
import sys
import json
import requests
import subprocess
import shutil

# Try importing config, default to some values if not found or running elsewhere
try:
    from config import SERVER_PORT, DEFAULT_LLM_MODEL, DEFAULT_TOP_K
except ImportError:
    SERVER_PORT = 8000
    DEFAULT_LLM_MODEL = "qwen3-coder"
    DEFAULT_TOP_K = "10"

LOCAL_RAG_URL = f"http://localhost:{SERVER_PORT}/query"

# Gatekeeper prompt instructing the local model to answer OR escalate
ROUTER_PROMPT = """You are a triage agent for a Java codebase.
You have been provided with context chunks from the codebase and a user's question.

RULES:
- If the context contains enough information to answer the question directly, answer it.
- Only output exactly: ESCALATE
  if ANY of these is true:
  - The context is empty or clearly irrelevant to the question
  - The question asks to implement or refactor something large
  - The question requires knowledge outside the provided context

Do not explain. Either answer the question or output ESCALATE.
"""

def check_dependencies():
    """Checks if required dependencies (node, npx) are available."""
    if not shutil.which("node"):
        print("❌ ERROR: 'node' is not installed or not in PATH.")
        sys.exit(1)
    if not shutil.which("npx"):
        print("❌ ERROR: 'npx' is not installed or not in PATH.")
        sys.exit(1)
    return True

def query_local_rag(question: str) -> dict:
    """Hits the local RAG server for retrieval and local generation."""
    print(f"🔍 Fetching context from local vector database...")
    try:
        # For our existing RAG server, /query expects: {"question": "...", "top_k": N}
        payload = {"question": question, "top_k": DEFAULT_TOP_K} 
        response = requests.post(LOCAL_RAG_URL, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Could not connect to the local RAG server.")
        print(f"   Make sure it is running on port {SERVER_PORT} (python rag/server.py)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR querying local RAG: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Smart Local-to-Cloud RAG Router (CLI-based)")
    parser.add_argument("question", type=str, help="The question to ask the codebase")
    parser.add_argument("--cloud-model", type=str, default=None, help="The Gemini model to use for escalation (optional)")
    args = parser.parse_args()

    check_dependencies()

    question = args.question
    print(f"\n🧠 Question: {question}")
    
    # Step 1: Hit Local RAG
    print(f"🤖 Routing to Local Gatekeeper ({DEFAULT_LLM_MODEL})...")
    
    rag_response = query_local_rag(question)
    
    if "error" in rag_response:
        print(f"❌ Local server returned error: {rag_response['error']}")
        sys.exit(1)
        
    # The server.py /query endpoint returns the context chunks in the 'results' field.
    chunks = rag_response.get("results", [])
    context_text = "\n\n".join([chunk.get("content", "") for chunk in chunks])
    
    # We will generate the local answer or triage decision here.
    local_answer = "" 
    
    print(f"   [Debug] Retrieved {len(chunks)} context chunks ({len(context_text)} characters). Context: ({context_text}")
    
    # Triage logic using Ollama directly (to force the ESCALATE behavior)
    gatekeeper_decision = ""
    import ollama
    try:
        client = ollama.Client(host="http://localhost:11434")
        prompt = f"{ROUTER_PROMPT}\n\nContext:\n{context_text}\n\nQuestion: {question}"
        triage = client.chat(
            model=DEFAULT_LLM_MODEL,
            messages=[{"role": "user", "content": prompt}]
        )
        gatekeeper_decision = triage.message.content.strip()
    except Exception:
        # Fallback if Ollama direct call fails (check if the original answer looked like a failure)
        if "I don't find enough information" in local_answer or len(local_answer) < 50:
            gatekeeper_decision = "ESCALATE"
        else:
            gatekeeper_decision = local_answer

    # Step 2: Evaluate Decision
    if gatekeeper_decision == "ESCALATE" or "ESCALATE" in gatekeeper_decision:
        print(f"☁️  Local model requested ESCALATION to Gemini CLI!")
        
        print("🚀 Invoking Gemini CLI with precise context payload...")
        try:
            # Systemic instructions to stop the CLI from acting like an autonomous agent
            system_prefix = (
                "SYSTEM INSTRUCTION: You are a standard Q&A assistant. "
                "You have been provided with ALL necessary code context below. "
                "DO NOT attempt to use tools, DO NOT read local files, and DO NOT run shell commands. "
                "Simply answer the question using the provided context text.\n\n"
            )
            
            cloud_prompt = (
                f"{system_prefix}"
                "You are an expert Java developer. Answer the following question using the provided context from a Java codebase.\n\n"
                f"Context:\n{context_text}\n\n"
                f"Question:\n{question}"
            )
            
            # Construct the CLI command
            # --approval-mode plan: Read-only mode, prevents it from trying to edit or run commands
            # -p -: Tells the CLI to read the prompt from stdin
            # -o text: Ensures we get raw text output
            cmd = ["npx", "--yes", "@google/gemini-cli", "--approval-mode", "plan", "-o", "text", "-p", "-"]
            if args.cloud_model:
                cmd.extend(["-m", args.cloud_model])
            
            print(f"   [CLI] Launching @google/gemini-cli (streaming via stdin)...")
            
            # Execute and pipe prompt to stdin, while streaming output to terminal
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=sys.stdout, stderr=sys.stderr, text=True)
            process.communicate(input=cloud_prompt)
            
            if process.returncode != 0:
                print(f"❌ Gemini CLI Error (exit code {process.returncode})")
            else:
                print("\n✅ CLOUD ANSWER COMPLETED.")
                print("==================================\n")
            
        except Exception as e:
            print(f"❌ Error invoking Gemini CLI: {e}")
            
    else:
        print("✅ LOCAL ANSWER (No cloud cost incurred!):")
        print("\n==================================")
        # If the gatekeeper gave a good answer, print it. If it was short, print the original RAG answer.
        final_answer = gatekeeper_decision if len(gatekeeper_decision) > 50 else local_answer
        print(final_answer)
        print("==================================\n")

if __name__ == "__main__":
    main()
