# RAG + Debug Agent - Quick Start

A Java codebase search and debugging system with two modes.

## 5-Minute Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Make sure Ollama is running
ollama serve &

# 3. Pull models (if not already done)
ollama pull nomic-embed-text
ollama pull mistral

# 4. Index your code (one-time)
python rag_system_ollama.py --index

# 5. Start using it
python rag_system_ollama.py --query "What is MyClass?"    # Quick lookup
python agent.py                                             # Debug mode
```

## Two Usage Modes

### Mode 1: RAG Queries (Fast Lookup)
```bash
python rag_system_ollama.py --query "What does UserService do?"
# Returns: Code explanation instantly
```
**Use for:** Understanding code, finding classes/methods, quick lookups

### Mode 2: Debug Agent (Problem Solving)
```bash
python agent.py
Problem Description> Why am I getting timeout errors?

# Agent analyzes, asks 3-4 strategic questions, queries RAG, provides diagnosis
# Takes 15-30 seconds, provides root cause + recommendations
```
**Use for:** Debugging issues, root cause analysis, complex problems

## What It Does

| Want | Use | Time |
|------|-----|------|
| "Show me UserService" | RAG query | <1 sec |
| "What is timeout error?" | RAG query | <1 sec |
| "Why am I getting timeouts?" | Agent | 20-30 sec |
| "Debug my NullPointerException" | Agent | 20-30 sec |

## Configuration

Edit `config.json` for:
- Models: `ollama.llm_model`, `ollama.embedding_model`
- Search: `retrieval.top_k`, `search.rerank_results`
- Debug: `debug.verbose`, `debug.log_chunks`

## Common Issues

**Agent hangs for >40 seconds?**
```json
{
  "retrieval": {"top_k": 5},
  "search": {"rerank_results": false}
}
```

**Not finding your code?**
```bash
rm -rf rag_db/
python rag_system_ollama.py --index
```

**Ollama not connecting?**
```bash
ollama list
# If missing models:
ollama pull mistral nomic-embed-text
```

## Architecture

```
Your Problem
    ↓
    Debug Agent (analyzes, creates 3-4 questions)
    ↓
    RAG System (vector search in your code)
    ↓
    Agent Analyzes (synthesizes code context)
    ↓
    Diagnostic Report (root causes + fixes)
```

## Files

- `agent.py` - Debug agent
- `rag_system_ollama.py` - Code search engine
- `config.json` - All settings
- `inspect_index.py` - View indexed content

## Examples

### Example 1: Quick Lookup
```bash
$ python rag_system_ollama.py --query "How is authentication implemented?"
Found: AuthService.java with login() method, token validation logic...
```

### Example 2: Debugging
```bash
$ python agent.py
Problem> Getting NullPointerException when users login

🤔 Formulating questions...
Q1: How is login() implemented?
Q2: What null checks exist?
Q3: How are tokens validated?

🔍 Querying code...
📊 Analyzing...

DIAGNOSTIC REPORT:
Root Cause: Missing null check on token before validation
Fix: Add if (token != null) check at line 45
Code: AuthService.java lines 40-50
```

### Example 3: Performance Issue
```bash
$ python agent.py --debug "API response time increased 10x after update"

Agent identifies:
- N+1 query problem in UserRepository
- Missing database indexes
- Inefficient caching

Recommendations:
- Batch queries in UserRepository
- Add index to user_id column
- Implement caching for user lookups
```

## Tips

**Better RAG results:**
- Be specific: "UserService.authenticate()" not "auth"
- Use exact class names from your code

**Better agent results:**
- Include error messages: "NullPointerException: user is null"
- Mention frequency: "Fails 10% of requests under load"
- Include context: "Happens after database update"

## Next

- RAG + Agent are now ready for your codebase
- Use RAG for quick lookups
- Use Agent for debugging complex issues
- See REFERENCE.md for full capabilities
- See TROUBLESHOOTING.md for issues
