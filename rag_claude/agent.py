#!/usr/bin/env python3
"""
Simple Debug Agent that uses RAG.
Analyzes problems and provides debugging help.
"""

import requests
from rag_system_ollama import RAGSystem


class CodeDebugAgent:
    """Simple debugging agent."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.rag = RAGSystem()
        self.ollama_url = self.rag.config.get('ollama.url', 'http://localhost:11434')
        self.model = self.rag.config.get('ollama.agent_model', 'mistral')

    def _extract_key_terms(self, problem: str) -> list:
        """Extract key class/method names and error terms from problem."""
        import re
        terms = []

        # Extract class names (e.g., XMLWriterHelper, ConversationStreamWriter)
        class_pattern = r'\b([A-Z][a-zA-Z0-9]*(?:Service|Helper|Writer|Manager|Util|Handler|Factory)?)\b'
        classes = re.findall(class_pattern, problem)
        terms.extend(classes[:3])  # Top 3 classes

        # Extract method names (e.g., writeCData, writeMessage)
        method_pattern = r'\.([a-z][a-zA-Z0-9]*)\('
        methods = re.findall(method_pattern, problem)
        terms.extend(methods[:2])  # Top 2 methods

        # Extract key error terms
        error_keywords = ['Exception', 'Error', 'surrogate', 'encoding', 'character', 'validation', 'sanitize', 'invalid']
        for keyword in error_keywords:
            if keyword.lower() in problem.lower():
                terms.append(keyword)

        return list(set(terms))[:5]  # Return unique terms, max 5

    def _generate_targeted_questions(self, problem: str) -> list:
        """Generate targeted questions based on error analysis."""
        key_terms = self._extract_key_terms(problem)

        questions = []

        # Question 1: Find the class/method involved
        if key_terms:
            primary_term = key_terms[0]
            questions.append(f"How does {primary_term} handle or process input data and what validation does it perform?")
        else:
            questions.append("What is the main class involved and how does it validate input?")

        # Question 2: Find error handling or character validation
        if any(term in problem.lower() for term in ['character', 'unicode', 'encoding', 'surrogate', 'utf']):
            questions.append("What character encoding validation or sanitization exists in the codebase?")
        else:
            questions.append("What error handling and validation exists before this operation?")

        # Question 3: Find where the invalid data comes from
        questions.append("Where in the pipeline is data transformed or passed before reaching this point?")

        return questions

    def _llm_call(self, prompt: str, max_tokens: int = None) -> str:
        """Call LLM with timeout."""
        try:
            if max_tokens is None:
                max_tokens = self.rag.config.get('agent.max_tokens_default', 150)
            temperature = self.rag.config.get('ollama.temperature', 0.7)
            timeout = self.rag.config.get('agent.timeout', 30)
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "num_predict": max_tokens,
                    "temperature": temperature,
                },
                timeout=timeout
            )
            if response.status_code != 200:
                return "Error: LLM request failed"
            return response.json()['response']
        except requests.Timeout:
            return "Error: Request timeout"
        except Exception as e:
            return f"Error: {str(e)[:50]}"

    def debug(self, problem: str) -> dict:
        """Simple debugging: ask questions, get answers."""
        results = {
            'problem': problem,
            'analysis': '',
            'recommendation': ''
        }

        # Get config values
        num_queries = self.rag.config.get('agent.num_queries', 3)
        problem_words = self.rag.config.get('agent.problem_words_to_extract', 3)
        context_length = self.rag.config.get('agent.context_snippet_length', 300)
        max_tokens_analysis = self.rag.config.get('agent.max_tokens_analysis', 100)
        max_tokens_recommendation = self.rag.config.get('agent.max_tokens_recommendation', 100)

        print("\n" + "="*70)
        print("DEBUG ANALYSIS")
        print("="*70)
        print(f"Problem: {problem}\n")

        # Step 1: Generate targeted questions based on error
        print(f"🔍 Querying codebase ({num_queries} queries)...")
        questions = self._generate_targeted_questions(problem)

        rag_results = {}
        for i, q in enumerate(questions[:num_queries], 1):
            try:
                print(f"  [{i}] Searching...", end=' ', flush=True)
                response = self.rag.query(q)
                rag_results[q] = response[:200] if response else "No results"
                print("✓")
            except Exception as e:
                print(f"✗ ({str(e)[:20]})")
                rag_results[q] = "Error querying"

        # Step 2: Root cause analysis
        print("\n💭 Analyzing...", end=' ', flush=True)
        analysis_prompt = f"""Based on this error: "{problem}"

Code context from codebase:
{str(rag_results)[:context_length]}

Perform a concise root cause analysis:
1. What is the immediate cause of the error?
2. What data or condition triggers it?
3. What is the underlying bug or design issue?

Be specific and reference the code if possible."""

        try:
            analysis = self._llm_call(analysis_prompt, max_tokens=max_tokens_analysis)
            print("✓\n")
        except:
            analysis = "Unable to analyze"
            print("✗\n")

        # Step 3: Actionable recommendation
        print("💡 Generating recommendation...", end=' ', flush=True)
        rec_prompt = f"""For this Java error: "{problem}"

Root cause: {analysis}

Provide a concrete fix with:
1. WHERE to fix it (which class/method)
2. WHAT to change (validation, error handling, etc)
3. HOW to implement it (code pattern or example)

Be specific and reference actual code if available."""

        try:
            rec = self._llm_call(rec_prompt, max_tokens=max_tokens_recommendation)
            print("✓\n")
        except:
            rec = "Check the code sections identified above"
            print("✗\n")

        results['analysis'] = analysis
        results['recommendation'] = rec

        return results

    def interactive(self):
        """Interactive mode."""
        num_queries = self.rag.config.get('agent.num_queries', 3)
        timeout = self.rag.config.get('agent.timeout', 30)
        print("\n" + "="*70)
        print(f"JAVA CODE DEBUG AGENT - {self.model}")
        print("="*70)
        print(f"Settings: {num_queries} queries, {timeout}s timeout")
        print("Describe a code problem. Type 'exit' to quit.")
        print("For multi-line input (stack traces), paste then press Enter twice.\n")

        while True:
            try:
                problem = input("Problem> ").strip()
                if not problem:
                    continue
                if problem.lower() == 'exit':
                    break

                # Handle multi-line pasted input
                # If input looks like it might continue, read more lines
                problem_lower = problem.lower()
                if any(x in problem_lower for x in ['exception', 'error', 'at ', 'caused by', 'stack trace']):
                    print("(Reading multi-line input... press Enter twice to finish)")
                    while True:
                        try:
                            line = input().strip()
                            if not line:
                                break
                            problem += "\n" + line
                        except EOFError:
                            break

                result = self.debug(problem)

                print("="*70)
                print("ANALYSIS:", result['analysis'])
                print("\nRECOMMENDATION:", result['recommendation'])
                print("="*70 + "\n")

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")


def main():
    import sys

    agent = CodeDebugAgent(verbose=False)

    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        problem = " ".join(sys.argv[2:])
        if not problem:
            print("Usage: python agent.py --debug 'Your problem'")
            sys.exit(1)

        result = agent.debug(problem)
        print("="*70)
        print("ANALYSIS:", result['analysis'])
        print("RECOMMENDATION:", result['recommendation'])
        print("="*70)
    else:
        agent.interactive()


if __name__ == "__main__":
    main()
