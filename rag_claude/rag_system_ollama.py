#!/usr/bin/env python3
"""
Production RAG system for Java codebases with vector embeddings.
Uses Ollama for embeddings and LLM, Chroma for vector storage.
Fully configurable via config.json.
"""

import json
import os
import re
from pathlib import Path
from typing import Optional
import requests
import chromadb


class Config:
    """Load and manage RAG configuration."""

    def __init__(self, config_path: str = "config.json"):
        self.path = Path(config_path)
        self.data = {}
        self.load()

    def load(self):
        """Load configuration from file."""
        if self.path.exists():
            with open(self.path) as f:
                self.data = json.load(f)
        else:
            self.data = self._default_config()

    def _default_config(self) -> dict:
        """Default configuration."""
        return {
            "ollama": {
                "url": "http://localhost:11434",
                "embedding_model": "nomic-embed-text",
                "rag_model": "mistral",
                "temperature": 0.7,
                "timeout": 120
            },
            "indexing": {
                "chunk_size": 2000,
                "overlap": 200,
                "patterns": ["*.java", "*.xml", "*.properties", "*.md"],
                "exclude_dirs": ["target/", "node_modules/", ".git/", "rag_db/"]
            },
            "retrieval": {
                "top_k": 10,
                "min_similarity": 0.0,
                "include_distances": True
            },
            "generation": {
                "max_tokens": 1024,
                "context_window_size": 4000,
                "system_prompt": "You are an expert Java developer. Answer questions about the codebase based on retrieved code context."
            },
            "chunking_strategy": {
                "extract_classes": True,
                "extract_methods": True,
                "extract_imports": True,
                "extract_annotations": True,
                "extract_javadoc": True,
                "max_chunk_chars": 2000
            },
            "search": {
                "use_hybrid_search": False,
                "keyword_weight": 0.3,
                "vector_weight": 0.7,
                "rerank_results": True
            },
            "debug": {
                "verbose": False,
                "log_chunks": False
            }
        }

    def get(self, key: str, default=None):
        """Get config value by dot notation (e.g., 'ollama.url')."""
        keys = key.split('.')
        value = self.data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default


class JavaCodeChunker:
    """Intelligently chunks Java source code."""

    def __init__(self, config: Config):
        self.config = config
        self.max_chunk_chars = config.get("chunking_strategy.max_chunk_chars", 2000)
        self.extract_javadoc = config.get("chunking_strategy.extract_javadoc", True)
        self.extract_annotations = config.get("chunking_strategy.extract_annotations", True)

    def chunk_file(self, content: str, file_path: str) -> list[dict]:
        """Split Java file into semantic chunks."""
        chunks = []

        # Extract Javadoc + class blocks
        if self.config.get("chunking_strategy.extract_classes"):
            javadoc_pattern = r'/\*\*.*?\*/'
            class_pattern = r'((?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+\w+\s*(?:extends|implements)?[^{]*\{(?:[^{}]|{[^}]*})*\})'

            for match in re.finditer(class_pattern, content, re.DOTALL):
                class_block = match.group(1)
                class_start = content[:match.start()].count('\n')

                # Look for preceding Javadoc (if configured)
                javadoc = ""
                if self.extract_javadoc and match.start() > 0:
                    preceding = content[:match.start()]
                    javadoc_match = re.search(javadoc_pattern, preceding, re.DOTALL)
                    if javadoc_match:
                        javadoc = javadoc_match.group(0)

                class_name_match = re.search(r'class\s+(\w+)', class_block)
                if class_name_match:
                    class_name = class_name_match.group(1)
                    full_content = (javadoc + "\n" + class_block) if javadoc else class_block

                    chunks.append({
                        'type': 'class',
                        'name': class_name,
                        'file': file_path,
                        'line': class_start + 1,
                        'content': class_block[:1000],
                        'full_content': full_content[:self.max_chunk_chars]
                    })

        # Extract methods with Javadoc
        if self.config.get("chunking_strategy.extract_methods"):
            method_pattern = r'((?:public|private|protected)?\s+(?:static\s+)?(?:synchronized\s+)?(?:\w+(?:<[^>]+>)?)\s+(\w+)\s*\([^)]*\)\s*(?:throws[^{]*)?\{[^}]*\})'
            javadoc_pattern = r'/\*\*.*?\*/'

            for match in re.finditer(method_pattern, content, re.DOTALL):
                method_block = match.group(1)
                method_name = match.group(2)
                method_start = content[:match.start()].count('\n')

                # Look for Javadoc (if configured)
                javadoc = ""
                if self.extract_javadoc and match.start() > 0:
                    preceding = content[:match.start()]
                    javadoc_match = re.search(javadoc_pattern, preceding, re.DOTALL)
                    if javadoc_match:
                        javadoc = javadoc_match.group(0)

                full_content = (javadoc + "\n" + method_block) if javadoc else method_block

                chunks.append({
                    'type': 'method',
                    'name': method_name,
                    'file': file_path,
                    'line': method_start + 1,
                    'content': method_block[:500],
                    'full_content': full_content[:self.max_chunk_chars]
                })

        # Extract annotations (if configured)
        if self.extract_annotations:
            annotation_pattern = r'@[A-Za-z_][\w.]*(?:\([^)]*\))?'
            for match in re.finditer(annotation_pattern, content):
                annotation = match.group(0)
                annotation_start = content[:match.start()].count('\n')

                chunks.append({
                    'type': 'annotation',
                    'name': annotation.split('(')[0],  # Get annotation name without args
                    'file': file_path,
                    'line': annotation_start + 1,
                    'content': annotation,
                    'full_content': annotation
                })

        # Extract package
        if self.config.get("chunking_strategy.extract_imports"):
            package_match = re.search(r'package\s+([\w.]+)', content)
            if package_match:
                chunks.append({
                    'type': 'package',
                    'name': package_match.group(1),
                    'file': file_path,
                    'line': 1,
                    'content': f"Package: {package_match.group(1)}",
                    'full_content': content[:2000]
                })

            # Extract imports
            imports = re.findall(r'import\s+([\w.*]+)', content)
            if imports:
                chunks.append({
                    'type': 'imports',
                    'name': 'Imports',
                    'file': file_path,
                    'line': 1,
                    'content': '\n'.join(imports),
                    'full_content': '\n'.join(imports)
                })

        # For XML/properties files, split into chunks
        if file_path.endswith(('.xml', '.properties', '.md')):
            chunk_size = self.config.get("indexing.chunk_size", 2000)
            lines = content.split('\n')
            for i in range(0, len(lines), chunk_size):
                chunk_lines = lines[i:i+chunk_size]
                if chunk_lines:
                    chunks.append({
                        'type': 'config' if file_path.endswith(('.xml', '.properties')) else 'doc',
                        'name': Path(file_path).name,
                        'file': file_path,
                        'line': i + 1,
                        'content': '\n'.join(chunk_lines),
                        'full_content': '\n'.join(chunk_lines)
                    })

        return chunks


class OllamaEmbeddings:
    """Generate embeddings using Ollama."""

    def __init__(self, config: Config):
        self.config = config
        self.url = config.get("ollama.url", "http://localhost:11434").rstrip('/')
        self.model = config.get("ollama.embedding_model", "nomic-embed-text")
        self._verify_model()

    def _verify_model(self):
        """Verify embedding model is available."""
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                model_names = [m['name'].split(':')[0] for m in models]
                if self.model not in model_names:
                    print(f"⚠ Model '{self.model}' not found.")
                    print(f"Install with: ollama pull {self.model}")
                else:
                    print(f"✓ Embedding model ready: {self.model}")
        except Exception as e:
            print(f"⚠ Could not verify Ollama: {e}")

    def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        try:
            response = requests.post(
                f"{self.url}/api/embed",
                json={"model": self.model, "input": text},
                timeout=self.config.get("ollama.timeout", 120)
            )
            if response.status_code == 200:
                return response.json()['embeddings'][0]
            return []
        except Exception as e:
            if self.config.get("debug.verbose"):
                print(f"Embedding error: {e}")
            return []


class RAGSystem:
    """Production RAG system with full configuration."""

    def __init__(self, config_path: str = "config.json"):
        self.config = Config(config_path)
        self.db_path = "./rag_db"

        # Initialize Chroma client
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(
            name="java_codebase",
            metadata={"hnsw:space": "cosine"}
        )

        # Initialize components
        self.embeddings = OllamaEmbeddings(self.config)
        self.chunker = JavaCodeChunker(self.config)
        self._all_docs_cache = None  # Cache for keyword search

        print(f"✓ Vector DB ready: {self.db_path}")
        self._print_config()

    def _print_config(self):
        """Print active configuration."""
        if self.config.get("debug.verbose"):
            print("\nActive Configuration:")
            print(f"  Embedding: {self.config.get('ollama.embedding_model')}")
            print(f"  LLM: {self.config.get('ollama.rag_model')}")
            print(f"  Top K: {self.config.get('retrieval.top_k')}")
            print(f"  Chunk size: {self.config.get('indexing.chunk_size')}")

    def index_java_file(self, file_path: str):
        """Index a single Java file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            chunks = self.chunker.chunk_file(content, file_path)
            log_chunks = self.config.get('debug.log_chunks', False)

            if log_chunks:
                print(f"\n{'='*70}")
                print(f"INDEXING: {file_path}")
                print(f"{'='*70}")

            indexed_count = 0
            for chunk in chunks:
                # Generate embedding
                embedding = self.embeddings.embed(chunk['full_content'])

                if embedding:
                    chunk_id = f"{file_path}:{chunk['type']}:{chunk['name']}:{chunk['line']}"

                    self.collection.add(
                        ids=[chunk_id],
                        documents=[chunk['full_content']],
                        metadatas=[{
                            'type': chunk['type'],
                            'name': chunk['name'],
                            'file': chunk['file'],
                            'line': chunk['line']
                        }],
                        embeddings=[embedding]
                    )
                    indexed_count += 1

                    if log_chunks:
                        print(f"\n  [{chunk['type'].upper()}] {chunk['name']}")
                        print(f"    Line: {chunk['line']}")
                        print(f"    Size: {len(chunk['full_content'])} chars")
                        print(f"    Preview: {chunk['full_content'][:100]}...")

            if self.config.get("debug.verbose"):
                print(f"✓ Indexed {file_path}: {indexed_count} chunks")
        except Exception as e:
            print(f"✗ Error indexing {file_path}: {e}")

    def index_directory(self, root_path: str):
        """Index entire directory."""
        patterns = self.config.get("indexing.patterns", ["*.java"])
        exclude_dirs = self.config.get("indexing.exclude_dirs", [])

        root = Path(root_path)
        count = 0

        for pattern in patterns:
            for file_path in root.rglob(pattern):
                if any(skip in str(file_path) for skip in exclude_dirs):
                    continue

                self.index_java_file(str(file_path))
                count += 1

        print(f"\n✓ Indexed {count} files. Total docs in DB: {self.collection.count()}")

    def _rerank_results(self, question: str, results: list, top_k: int = 10) -> list:
        """Rerank results based on relevance to question."""
        if not results:
            return results

        # Extract keywords from question
        question_words = set(word.lower() for word in re.findall(r'\w+', question))
        question_words.discard('what')
        question_words.discard('how')
        question_words.discard('why')
        question_words.discard('where')
        question_words.discard('when')
        question_words.discard('does')
        question_words.discard('is')
        question_words.discard('a')
        question_words.discard('the')
        question_words.discard('in')
        question_words.discard('of')

        # Rerank by relevance score
        reranked = []
        for result in results:
            metadata = result['metadata']
            doc = result['doc']
            combined_score = result['combined_score']

            # Calculate relevance boost
            relevance_boost = 0

            # Boost for keyword matches in name (highest priority)
            name_lower = metadata['name'].lower()
            matching_keywords = question_words & set(word.lower() for word in re.findall(r'\w+', name_lower))
            relevance_boost += len(matching_keywords) * 0.15

            # Boost for keyword matches in content
            doc_lower = doc.lower()
            doc_keywords = set(word.lower() for word in re.findall(r'\w+', doc_lower))
            content_matches = len(question_words & doc_keywords)
            relevance_boost += min(content_matches * 0.05, 0.2)  # Cap at 0.2

            # Boost based on chunk type (method > class > config > other)
            type_boost = {
                'method': 0.1,
                'class': 0.05,
                'annotation': 0.03,
                'imports': 0.02,
                'package': 0.01,
                'config': 0.01,
                'doc': 0.01,
                'other': 0
            }
            relevance_boost += type_boost.get(metadata['type'], 0)

            # Final reranked score
            final_score = min(combined_score + relevance_boost, 1.0)

            reranked.append({
                **result,
                'rerank_score': final_score,
                'relevance_boost': relevance_boost
            })

        # Sort by rerank score
        reranked.sort(key=lambda x: x['rerank_score'], reverse=True)
        return reranked[:top_k]

    def _keyword_search(self, question: str, top_k: int = 10) -> list:
        """Simple keyword-based search in the database."""
        if self._all_docs_cache is None:
            # Load all documents once
            all_results = self.collection.get(include=["documents", "metadatas"])
            self._all_docs_cache = list(zip(
                all_results['documents'],
                all_results['metadatas']
            ))

        # Extract keywords from question
        keywords = set(question.lower().split())
        keywords.discard('what')
        keywords.discard('how')
        keywords.discard('explain')
        keywords.discard('does')
        keywords.discard('do')
        keywords.discard('the')
        keywords.discard('is')
        keywords.discard('a')

        # Score documents by keyword matches
        scored_docs = []
        for doc, metadata in self._all_docs_cache:
            score = 0
            content_lower = (metadata['name'] + ' ' + doc).lower()

            for keyword in keywords:
                if keyword in content_lower:
                    # Boost score for name matches
                    if keyword in metadata['name'].lower():
                        score += 10
                    else:
                        score += 1

            if score > 0:
                scored_docs.append((score, doc, metadata))

        # Sort by score and return top_k
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return [(doc, metadata) for _, doc, metadata in scored_docs[:top_k]]

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama LLM."""
        try:
            payload = {
                "model": self.config.get('ollama.rag_model'),
                "prompt": prompt,
                "temperature": self.config.get('ollama.temperature', 0.7),
                "stream": False,
            }

            # Add max_tokens if configured
            max_tokens = self.config.get('generation.max_tokens')
            if max_tokens:
                payload["num_predict"] = max_tokens  # Ollama uses num_predict

            response = requests.post(
                f"{self.config.get('ollama.url')}/api/generate",
                json=payload,
                timeout=self.config.get('ollama.timeout', 120)
            )
            response.raise_for_status()
            return response.json()['response']
        except Exception as e:
            return f"Error: {e}"

    def query(self, question: str) -> str:
        """Query using vector search only (fast, no loops)."""
        if self.collection.count() == 0:
            return "No indexed content. Run: python rag_system_ollama.py --index"

        # Get configuration
        top_k = self.config.get('retrieval.top_k', 5)
        min_similarity = self.config.get('retrieval.min_similarity', 0.0)
        context_window = self.config.get('generation.context_window_size', 4000)
        log_chunks = self.config.get('debug.log_chunks', False)

        # Simple vector search (no loops, no hybrid)
        question_embedding = self.embeddings.embed(question)
        if not question_embedding:
            return "Error generating embedding"

        try:
            results = self.collection.query(
                query_embeddings=[question_embedding],
                n_results=top_k
            )
        except Exception as e:
            return f"Error querying: {str(e)[:100]}"

        combined = []
        if results and results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i]
                distance = results['distances'][0][i]
                similarity = 1 - distance

                combined.append({
                    'doc': doc,
                    'metadata': metadata,
                    'combined_score': similarity,
                    'method': 'vector'
                })

        # Log results if enabled
        if log_chunks and combined:
            print("\n[RAG] Found", len(combined), "results")

        # Build context from top results
        context = "# Retrieved Code Context\n\n"
        valid_results = 0

        for result in combined[:top_k]:
            metadata = result['metadata']
            doc = result['doc']
            score = result['combined_score']

            if score < min_similarity:
                continue

            valid_results += 1
            context += f"## {metadata['type'].upper()}: {metadata['name']}\n"
            context += f"File: {metadata['file']} (line {metadata['line']})\n"
            context += f"Relevance: {score:.0%}\n"
            context += f"```java\n{doc[:500]}\n```\n\n"

            if len(context) > context_window:
                break

        if valid_results == 0:
            return "No relevant code found for your question. Try rephrasing or indexing more files."

        # Generate answer
        system_prompt = self.config.get(
            'generation.system_prompt',
            'You are an expert Java developer.'
        )

        prompt = f"""{system_prompt}

{context}

Question: {question}

Answer:"""

        if self.config.get("debug.verbose"):
            print(f"\nDebug: Retrieved {valid_results} relevant chunks (vector search)")
            print(f"Debug: Context length: {len(context)} chars\n")

        return self._call_ollama(prompt)

    def chat(self):
        """Interactive chat mode."""
        print("\n" + "="*70)
        print("RAG System - Java Codebase Vector Search")
        print("="*70)
        print(f"Vector DB documents: {self.collection.count()}")
        print(f"LLM: {self.config.get('ollama.rag_model')}")
        print(f"Embedding: {self.config.get('ollama.embedding_model')}")
        print(f"Top K: {self.config.get('retrieval.top_k')}")
        print(f"Min Similarity: {self.config.get('retrieval.min_similarity'):.1%}")

        debug_mode = "🔍 DEBUG MODE ON" if self.config.get("debug.log_chunks") else ""
        if debug_mode:
            print(f"\n{debug_mode}")
            if self.config.get("debug.log_chunks"):
                print("  ✓ Showing retrieved chunks")
            if self.config.get("debug.log_embeddings"):
                print("  ✓ Showing embedding info")

        print("\nCommands: 'exit', 'config', 'status'")
        print("-" * 70 + "\n")

        while True:
            try:
                question = input("Q> ").strip()

                if not question:
                    continue
                if question.lower() == 'exit':
                    break
                if question.lower() == 'status':
                    print(f"\nDocuments in DB: {self.collection.count()}\n")
                    continue
                if question.lower() == 'config':
                    self._print_config()
                    print()
                    continue

                print("\n🔍 Searching vectors...\n")
                answer = self.query(question)
                print(answer + "\n")

            except KeyboardInterrupt:
                print("\n")
                break
            except Exception as e:
                print(f"Error: {e}\n")


def main():
    import sys

    rag = RAGSystem()

    if len(sys.argv) > 1 and sys.argv[1] == "--index":
        repo_root = Path(__file__).parent.parent
        print(f"Indexing: {repo_root}")
        rag.index_directory(str(repo_root))
    elif len(sys.argv) > 1 and sys.argv[1] == "--query":
        query = " ".join(sys.argv[2:])
        print(rag.query(query))
    else:
        if rag.collection.count() == 0:
            print("No indexed content. Run: python rag_system_ollama.py --index")
            sys.exit(1)
        rag.chat()


if __name__ == "__main__":
    main()
