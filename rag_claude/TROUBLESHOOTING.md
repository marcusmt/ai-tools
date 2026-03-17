# Troubleshooting

## Agent/RAG Issues

### Agent Takes 60+ Seconds
**Fix:**
```json
{
  "retrieval": {"top_k": 5},
  "search": {"rerank_results": false},
  "ollama": {"llm_model": "neural-chat"}
}
```

### Agent Hangs / Won't Respond
**Check Ollama:**
```bash
ollama list
ollama pull mistral
# Restart if needed:
pkill ollama
ollama serve &
```

**Kill stuck process:**
```bash
pkill -f agent.py
python agent.py --debug "test"
```

### No Results Found
**Re-index code:**
```bash
rm -rf rag_db/
python rag_system_ollama.py --index
```

**Check indexing:**
```bash
python inspect_index.py
# Then search for: MyClass
```

### Poor/Generic Recommendations
**Better problem description:**
- Include error message: "NullPointerException: user is null"
- Mention frequency: "Fails 20% of requests"
- Add context: "Only happens under load"
- Include stack trace if available

**Check RAG can find code:**
```bash
python rag_system_ollama.py --query "MyService"
# Should return results about MyService
```

### "Connection refused" Error
**Ollama not running:**
```bash
ollama serve &
```

**Wrong Ollama URL:**
```bash
# Check config.json
"ollama": {"url": "http://localhost:11434"}
```

### Agent Gives Wrong Diagnosis
**Increase verbosity:**
```json
{"debug": {"verbose": true, "log_chunks": true}}
```

**Run with more context:**
```bash
python agent.py --debug "Detailed problem description with error messages"
```

**Check if RAG finding relevant code:**
```bash
python inspect_index.py
# Search for keywords from your problem
```

### Memory Usage High
**Reduce scope:**
```json
{
  "retrieval": {"top_k": 5},
  "generation": {"context_window_size": 2000}
}
```

### Agent Stuck in Loop
**Should be fixed, but if still happening:**
- Limit questions: Edit agent.py line 20: `return questions[:3]`
- Lower timeout: Edit agent.py `_call_agent_llm(timeout=30)`
- Restart: `pkill agent.py`

### Keyboard Interrupt (Ctrl+C) Doesn't Work
**Kill from another terminal:**
```bash
pkill -9 -f agent.py
```

---

## Configuration Issues

### Wrong Model Errors
```bash
# Check available models
ollama list

# Install if missing
ollama pull mistral
ollama pull nomic-embed-text
```

### Timeout Issues
**Increase timeouts in agent.py:**
```python
# Line ~55
_call_agent_llm(prompt, timeout=120)  # Was 60
```

**Or reduce load:**
```json
{
  "retrieval": {"top_k": 5},
  "search": {"rerank_results": false}
}
```

### Database Errors
```bash
# Reset vector DB
rm -rf rag_db/

# Rebuild
python rag_system_ollama.py --index
```

---

## Quick Fix Checklist

- [ ] Ollama running? `ollama list`
- [ ] Models installed? `ollama pull mistral nomic-embed-text`
- [ ] Code indexed? `python rag_system_ollama.py --index`
- [ ] Problem description detailed?
- [ ] Config settings reasonable? `cat config.json | grep top_k`
- [ ] Try simpler problem first? `python agent.py --debug "test"`
- [ ] Check system resources? `free -h`

---

## Performance Tuning

**Slow queries?**
```json
{
  "retrieval": {"top_k": 5},
  "search": {"rerank_results": false},
  "ollama": {"llm_model": "neural-chat"}
}
```

**Poor quality?**
```json
{
  "retrieval": {"top_k": 20},
  "search": {"rerank_top_k": 15},
  "ollama": {"llm_model": "orca"}
}
```

**Balanced (default)?**
```json
{
  "retrieval": {"top_k": 10},
  "search": {"rerank_results": true},
  "ollama": {"llm_model": "mistral"}
}
```

---

## Getting Help

Include when reporting issues:
1. What you asked: "NullPointerException at line 45"
2. What happened: "Agent took 2 minutes then hung"
3. Output: Show the error message
4. Config: Show relevant config.json settings
5. System: `free -h`, `ollama list`

Example:
```
Problem: "Getting timeout errors"
Agent output: Hangs after Step 2
Config: top_k=20, rerank=true
Ollama: mistral, nomic-embed-text running
Memory: 8GB available
```

---

## Still Stuck?

**Complete reset:**
```bash
# 1. Kill all processes
pkill ollama
pkill -f agent.py

# 2. Clear data
rm -rf rag_db/

# 3. Restart
ollama serve &
sleep 2
python rag_system_ollama.py --index
python agent.py --debug "simple test"
```

**Minimal test:**
```bash
# Just RAG (no agent)
python rag_system_ollama.py --query "MyService"

# If this works, agent issue
# If this doesn't, RAG/index issue
```
