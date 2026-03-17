#!/usr/bin/env python3
"""
Quick demo of the RAG system to show how it works.
"""

from rag_system_ollama import RAGSystem, OllamaEmbeddings, JavaCodeChunker
from pathlib import Path

def demo():
    print("="*70)
    print("RAG System Demo - Java Codebase Vector Search")
    print("="*70)

    # Initialize
    print("\n1. Initializing RAG system...")
    rag = RAGSystem()

    # Check database status
    print(f"\n2. Vector database status:")
    print(f"   Documents indexed: {rag.collection.count()}")

    if rag.collection.count() == 0:
        print("\n3. No indexed content yet. Indexing repository...")
        repo_root = Path(__file__).parent.parent
        rag.index_directory(str(repo_root))

    # Demo queries
    print(f"\n4. Indexed {rag.collection.count()} documents. Ready for queries!")
    print("\n5. Example queries to try:")
    print("   - What is this application?")
    print("   - How does authentication work?")
    print("   - What are the main modules?")
    print("   - Explain the log system")

    # Interactive mode
    print("\n6. Starting interactive mode...")
    print("   (Type 'exit' to quit)\n")
    rag.chat()


if __name__ == "__main__":
    demo()
