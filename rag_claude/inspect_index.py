#!/usr/bin/env python3
"""
Diagnostic tool to inspect what's actually in the vector database.
"""

import json
from pathlib import Path
import chromadb


def inspect_database(db_path: str = "./rag_db"):
    """Inspect the vector database."""
    print("="*70)
    print("Vector Database Inspector")
    print("="*70)

    try:
        client = chromadb.PersistentClient(path=db_path)
        collection = client.get_or_create_collection(name="java_codebase")

        count = collection.count()
        print(f"\n✓ Connected to vector database: {db_path}")
        print(f"✓ Total documents in collection: {count}\n")

        if count == 0:
            print("Database is empty. Run: python rag_system_ollama.py --index")
            return

        # Get all documents
        all_results = collection.get(include=["documents", "metadatas"])

        print("Database Contents:")
        print("-" * 70)

        # Organize by type and file
        by_type = {}
        by_file = {}

        for i, metadata in enumerate(all_results['metadatas']):
            chunk_type = metadata['type']
            file_path = metadata['file']
            name = metadata['name']
            line = metadata['line']
            doc = all_results['documents'][i]

            # By type
            if chunk_type not in by_type:
                by_type[chunk_type] = []
            by_type[chunk_type].append({
                'name': name,
                'file': file_path,
                'line': line,
                'size': len(doc)
            })

            # By file
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append({
                'type': chunk_type,
                'name': name,
                'line': line
            })

        # Print by type
        print("\n📊 BY TYPE:")
        for chunk_type in sorted(by_type.keys()):
            items = by_type[chunk_type]
            print(f"\n  {chunk_type.upper()} ({len(items)} items):")
            for item in sorted(items, key=lambda x: x['name'])[:10]:  # First 10
                print(f"    - {item['name']} ({item['file']}, line {item['line']}, {item['size']} chars)")
            if len(items) > 10:
                print(f"    ... and {len(items) - 10} more")

        # Print by file
        print("\n\n📁 BY FILE:")
        for file_path in sorted(by_file.keys())[:10]:  # First 10 files
            items = by_file[file_path]
            print(f"\n  {file_path} ({len(items)} chunks):")
            for item in items:
                print(f"    - [{item['type']}] {item['name']} (line {item['line']})")

        if len(by_file) > 10:
            print(f"\n  ... and {len(by_file) - 10} more files")

        # Search for a specific term
        print("\n\n🔍 SEARCH BY NAME:")
        search_term = input("Enter class/method name to search (or press Enter to skip): ").strip()

        if search_term:
            matches = []
            for i, metadata in enumerate(all_results['metadatas']):
                if search_term.lower() in metadata['name'].lower():
                    matches.append({
                        'type': metadata['type'],
                        'name': metadata['name'],
                        'file': metadata['file'],
                        'line': metadata['line'],
                        'doc': all_results['documents'][i]
                    })

            if matches:
                print(f"\n✓ Found {len(matches)} matching chunks:")
                for match in matches:
                    print(f"\n  [{match['type']}] {match['name']}")
                    print(f"  File: {match['file']} (line {match['line']})")
                    print(f"  Size: {len(match['doc'])} chars")
                    print(f"  Content preview:\n  {match['doc'][:200]}...")
            else:
                print(f"\n✗ No chunks found matching '{search_term}'")

        # Statistics
        print("\n\n📈 STATISTICS:")
        sizes = [len(doc) for doc in all_results['documents']]
        print(f"  Total documents: {len(sizes)}")
        print(f"  Average chunk size: {sum(sizes) // len(sizes)} chars")
        print(f"  Min chunk size: {min(sizes)} chars")
        print(f"  Max chunk size: {max(sizes)} chars")
        print(f"  Unique files: {len(by_file)}")
        print(f"  Chunk types: {', '.join(sorted(by_type.keys()))}")

    except Exception as e:
        print(f"✗ Error: {e}")
        print(f"Make sure the database exists at: {db_path}")


if __name__ == "__main__":
    inspect_database()
