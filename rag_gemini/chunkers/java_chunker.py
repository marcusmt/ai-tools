"""
Tree-sitter based Java source code chunker.
Splits Java files at class and method boundaries, preserving Javadoc,
annotations, and enough surrounding context for accurate retrieval.
"""

from __future__ import annotations

import tree_sitter_java as tsjava
from tree_sitter import Language, Parser
from pathlib import Path

JAVA_LANGUAGE = Language(tsjava.language())

# AST node types we extract as individual chunks
_CLASS_TYPES = {"class_declaration", "interface_declaration", "enum_declaration", "record_declaration"}
_METHOD_TYPES = {"method_declaration", "constructor_declaration"}


def _get_parser() -> Parser:
    parser = Parser(JAVA_LANGUAGE)
    return parser


def _leading_comment(source_bytes: bytes, node) -> str:
    """Grab the Javadoc / block-comment immediately above a node."""
    prev = node.prev_named_sibling
    if prev and prev.type in ("block_comment", "line_comment"):
        return source_bytes[prev.start_byte:prev.end_byte].decode("utf-8", errors="replace") + "\n"
    return ""


def _annotations(source_bytes: bytes, node) -> str:
    """Collect all annotation nodes that are children of the parent and precede this node."""
    parts: list[str] = []
    for child in (node.parent.children if node.parent else []):
        if child.type == "marker_annotation" or child.type == "annotation":
            if child.end_byte <= node.start_byte:
                parts.append(source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace"))
    return "\n".join(parts) + "\n" if parts else ""


def _node_text(source_bytes: bytes, node) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def chunk_java_file(file_path: Path, max_chars: int = 4000) -> list[dict]:
    """
    Parse a Java file and return a list of chunk dicts.

    Each chunk dict has:
      - content: str  (the code text)
      - chunk_type: str  ("class" | "method" | "file")
      - start_line: int
      - end_line: int
    """
    source = file_path.read_bytes()
    parser = _get_parser()
    tree = parser.parse(source)
    root = tree.root_node
    chunks: list[dict] = []

    # Collect the package and import block once
    header_parts: list[str] = []
    for child in root.children:
        if child.type in ("package_declaration", "import_declaration"):
            header_parts.append(_node_text(source, child))
        else:
            break
    file_header = "\n".join(header_parts) + "\n\n" if header_parts else ""

    def _walk(node):
        if node.type in _CLASS_TYPES:
            _process_class(node)
        else:
            for child in node.children:
                _walk(child)

    def _process_class(class_node):
        # First, emit each method/constructor as its own chunk
        method_ranges: list[tuple[int, int]] = []
        for child in class_node.children:
            body = child
            if child.type == "class_body":
                body = child
            elif child.type in _METHOD_TYPES:
                body = child  # shouldn't happen at this level, but safety
            else:
                continue

            if body.type == "class_body":
                for member in body.children:
                    if member.type in _METHOD_TYPES:
                        comment = _leading_comment(source, member)
                        text = comment + _node_text(source, member)
                        # If single method is too large, keep it anyway (it's a logical unit)
                        chunks.append({
                            "content": file_header + text,
                            "chunk_type": "method",
                            "start_line": member.start_point[0] + 1,
                            "end_line": member.end_point[0] + 1,
                        })
                        method_ranges.append((member.start_byte, member.end_byte))
                    # Recurse into nested classes
                    elif member.type in _CLASS_TYPES:
                        _process_class(member)

        # Emit a "class skeleton" chunk: the class with method bodies stripped
        class_text = _node_text(source, class_node)
        # Build skeleton by replacing method bodies with "{ ... }"
        skeleton = _build_skeleton(source, class_node, method_ranges)
        if skeleton:
            comment = _leading_comment(source, class_node)
            chunks.append({
                "content": file_header + comment + skeleton,
                "chunk_type": "class",
                "start_line": class_node.start_point[0] + 1,
                "end_line": class_node.end_point[0] + 1,
            })

    def _build_skeleton(source_bytes: bytes, class_node, method_ranges: list[tuple[int, int]]) -> str:
        """Replace method bodies with `{ /* ... */ }` to create a compact class overview."""
        text = source_bytes[class_node.start_byte:class_node.end_byte]
        offset = class_node.start_byte
        result_parts: list[str] = []
        pos = 0
        for m_start, m_end in sorted(method_ranges):
            rel_start = m_start - offset
            rel_end = m_end - offset
            if rel_start < 0 or rel_end > len(text):
                continue
            result_parts.append(text[pos:rel_start].decode("utf-8", errors="replace"))
            # keep the method signature (up to the opening brace) + stub
            method_bytes = text[rel_start:rel_end]
            method_str = method_bytes.decode("utf-8", errors="replace")
            brace_idx = method_str.find("{")
            if brace_idx != -1:
                result_parts.append(method_str[:brace_idx] + "{ /* ... */ }")
            else:
                result_parts.append(method_str)
            pos = rel_end
        result_parts.append(text[pos:].decode("utf-8", errors="replace"))
        return "".join(result_parts)

    _walk(root)

    # Fallback: if the file had no recognized class declarations, chunk the whole file
    if not chunks:
        full_text = source.decode("utf-8", errors="replace")
        chunks.append({
            "content": full_text,
            "chunk_type": "file",
            "start_line": 1,
            "end_line": full_text.count("\n") + 1,
        })

    return chunks
