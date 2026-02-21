import re
from pathlib import Path

from .deps import HAS_BM25, BM25Okapi
from .types import BM25Index


def _tokenize_code(text: str) -> list[str]:
    """Simple code-aware tokenizer: split on non-alphanumeric, lowercase."""
    return [t.lower() for t in re.split(r"[^a-zA-Z0-9_]+", text) if len(t) > 1]


def build_bm25_index(all_files: list[Path], root: Path) -> BM25Index | None:
    """
    Build a BM25 index over all PHP files in the repo.
    Files are split into chunks on blank lines (max 20 lines each).
    """
    if not HAS_BM25:
        return None

    chunks = []
    chunk_files = []
    tokenized = []

    for filepath in all_files:
        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel_path = str(filepath.relative_to(root)) if root in filepath.parents else str(filepath)
        lines = source.split("\n")

        # Split into chunks on blank lines, max 20 lines
        current_chunk = []
        for line in lines:
            if not line.strip() and current_chunk:
                chunk_text = "\n".join(current_chunk)
                if len(chunk_text.strip()) > 20:
                    chunks.append(chunk_text)
                    chunk_files.append(rel_path)
                    tokenized.append(_tokenize_code(chunk_text))
                current_chunk = []
            else:
                current_chunk.append(line)
                if len(current_chunk) >= 20:
                    chunk_text = "\n".join(current_chunk)
                    if len(chunk_text.strip()) > 20:
                        chunks.append(chunk_text)
                        chunk_files.append(rel_path)
                        tokenized.append(_tokenize_code(chunk_text))
                    current_chunk = []

        # Flush remaining
        if current_chunk:
            chunk_text = "\n".join(current_chunk)
            if len(chunk_text.strip()) > 20:
                chunks.append(chunk_text)
                chunk_files.append(rel_path)
                tokenized.append(_tokenize_code(chunk_text))

    if not tokenized:
        return None

    bm25 = BM25Okapi(tokenized)
    return BM25Index(bm25=bm25, chunks=chunks, chunk_files=chunk_files)


def retrieve_bm25_context(
    span_text: str,
    adjacent_context: str,
    index: BM25Index,
    filepath: str,
    max_tokens: int = 1024,
    top_k: int = 5,
    debug: bool = False,
) -> str | tuple[str, dict]:
    """
    Retrieve relevant code chunks from other files using BM25.
    Query = span text + surrounding lines. Excludes chunks from same file.

    When debug=True, returns (context_str, debug_info) with diagnostic details.
    """
    query = _tokenize_code(span_text + " " + adjacent_context)
    char_budget = max_tokens * 4
    if not query:
        if debug:
            return "", {"query_tokens": [], "scored_chunks": [], "budget": {"used_chars": 0, "max_chars": char_budget}}
        return ""

    scores = index.bm25.get_scores(query)

    # Get top-k indices, excluding same file
    scored = [
        (i, s) for i, s in enumerate(scores)
        if index.chunk_files[i] != filepath and s > 0
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Deduplicate by file (take best chunk per file)
    seen_files = set()
    selected = []
    for i, score in scored[:top_k * 2]:
        f = index.chunk_files[i]
        if f in seen_files:
            continue
        seen_files.add(f)
        selected.append((i, score))
        if len(selected) >= top_k:
            break

    if not selected:
        if debug:
            return "", {"query_tokens": query, "scored_chunks": [], "budget": {"used_chars": 0, "max_chars": char_budget}}
        return ""

    # Concatenate up to token budget
    parts = []
    total = 0
    chunk_details = []
    for i, score in selected:
        chunk = f"// --- {index.chunk_files[i]} ---\n{index.chunks[i]}"
        if total + len(chunk) > char_budget:
            if debug:
                chunk_details.append({"file": index.chunk_files[i], "score": round(float(score), 2), "selected": False, "length": len(chunk)})
            break
        parts.append(chunk)
        total += len(chunk)
        if debug:
            chunk_details.append({"file": index.chunk_files[i], "score": round(float(score), 2), "selected": True, "length": len(chunk)})

    if not parts:
        if debug:
            return "", {"query_tokens": query, "scored_chunks": chunk_details, "budget": {"used_chars": 0, "max_chars": char_budget}}
        return ""

    result = "\n\n".join(parts) + "\n\n"
    if debug:
        debug_info = {
            "query_tokens": query,
            "scored_chunks": chunk_details,
            "budget": {"used_chars": total, "max_chars": char_budget},
        }
        return result, debug_info
    return result
