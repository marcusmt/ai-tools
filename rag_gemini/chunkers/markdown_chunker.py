"""
Header-aware Markdown chunker.
Splits Markdown at ## headings, keeping titles in each chunk for context.
Large sections are further split at paragraph boundaries.
"""

from __future__ import annotations

import re
from pathlib import Path


_HEADER_RE = re.compile(r"^(#{1,3})\s+", re.MULTILINE)


def chunk_markdown_file(
    file_path: Path,
    max_chars: int = 4000,
    overlap_chars: int = 200,
) -> list[dict]:
    """
    Split a Markdown file into chunks.

    Returns a list of dicts with:
      - content: str
      - chunk_type: "doc-section"
      - start_line: int
      - end_line: int
    """
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines(keepalinenums := True)  # keep \n
    # Actually, splitlines drops \n — re-add for char counting
    lines = text.split("\n")

    # Find heading positions
    headings: list[tuple[int, str]] = []  # (line_index, heading_text)
    for i, line in enumerate(lines):
        if _HEADER_RE.match(line):
            headings.append((i, line.strip()))

    if not headings:
        # No headings → single chunk
        return [_make_chunk(text, "doc-section", 1, len(lines))]

    sections: list[tuple[int, int, str]] = []  # (start_line_idx, end_line_idx, heading)
    for idx, (line_idx, heading) in enumerate(headings):
        next_line = headings[idx + 1][0] if idx + 1 < len(headings) else len(lines)
        sections.append((line_idx, next_line, heading))

    # If there's content before the first heading, include it
    if headings[0][0] > 0:
        preamble_end = headings[0][0]
        preamble = "\n".join(lines[:preamble_end])
        if preamble.strip():
            sections.insert(0, (0, preamble_end, "(preamble)"))

    chunks: list[dict] = []
    for start_idx, end_idx, heading in sections:
        section_text = "\n".join(lines[start_idx:end_idx])
        if len(section_text) <= max_chars:
            chunks.append(_make_chunk(section_text, "doc-section", start_idx + 1, end_idx))
        else:
            # Split large section at paragraph boundaries (double newline)
            sub_chunks = _split_large_section(
                section_text, heading, max_chars, overlap_chars, start_idx
            )
            chunks.extend(sub_chunks)

    return chunks


def _make_chunk(content: str, chunk_type: str, start_line: int, end_line: int) -> dict:
    return {
        "content": content.strip(),
        "chunk_type": chunk_type,
        "start_line": start_line,
        "end_line": end_line,
    }


def _split_large_section(
    text: str,
    heading: str,
    max_chars: int,
    overlap_chars: int,
    base_line_idx: int,
) -> list[dict]:
    """Split a section that exceeds max_chars at paragraph boundaries."""
    paragraphs = re.split(r"\n\n+", text)
    chunks: list[dict] = []
    current = ""
    current_start = base_line_idx

    for para in paragraphs:
        if current and len(current) + len(para) + 2 > max_chars:
            line_count = current.count("\n")
            chunks.append(_make_chunk(
                current, "doc-section",
                current_start + 1,
                current_start + line_count + 1,
            ))
            # Overlap: keep the last `overlap_chars` as prefix for the next chunk
            overlap = current[-overlap_chars:] if len(current) > overlap_chars else ""
            current_start = current_start + line_count
            current = f"{heading}\n\n{overlap}\n\n{para}" if overlap else f"{heading}\n\n{para}"
        else:
            current = f"{current}\n\n{para}" if current else para

    if current.strip():
        line_count = current.count("\n")
        chunks.append(_make_chunk(
            current, "doc-section",
            current_start + 1,
            current_start + line_count + 1,
        ))

    return chunks
