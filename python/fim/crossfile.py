import re
from pathlib import Path


def _resolve_lang_config(lang_config):
    if lang_config is None:
        from fim.language import PHP
        return PHP
    return lang_config


def extract_file_signature(
    source: str,
    filepath: Path,
    referenced_symbols: set[str] | None = None,
    max_lines: int = 40,
    lang_config=None,
) -> str:
    """
    Extract a compact "signature" of a source file.
    Delegates to lang_config.extract_signature().
    """
    lc = _resolve_lang_config(lang_config)
    return lc.extract_signature(source, filepath, referenced_symbols, max_lines)


def _extract_referenced_symbols(source: str, lang_config=None) -> set[str]:
    """
    Extract identifiers referenced in a source file.
    Delegates to lang_config.extract_referenced_symbols().
    """
    lc = _resolve_lang_config(lang_config)
    return lc.extract_referenced_symbols(source)


def find_related_files(
    filepath: Path,
    all_files: list[Path],
    root: Path,
    source: str,
    lang_config=None,
) -> list[Path]:
    """
    Find files that are relevant context for a given file.
    Only includes files actually referenced via imports/requires — no
    same-directory heuristic (which causes context bloat).
    """
    lc = _resolve_lang_config(lang_config)
    related = []

    use_classes = lc.extract_imports(source)
    require_files = lc.extract_require_files(source)

    for f in all_files:
        if f == filepath:
            continue
        if f.stem in use_classes or f.stem in require_files:
            related.append(f)

    return related[:5]


def build_cross_file_context(
    filepath: Path,
    all_files: list[Path],
    root: Path,
    source: str,
    max_tokens: int = 1024,
    lang_config=None,
    debug: bool = False,
) -> str | tuple[str, dict]:
    """
    Build dependency-based cross-file context string to prepend to the FIM prefix.
    Filters signatures to only include symbols actually referenced by the target file.

    When debug=True, returns (context_str, debug_info) with diagnostic details.
    """
    lc = _resolve_lang_config(lang_config)
    related = find_related_files(filepath, all_files, root, source, lang_config=lc)
    if not related:
        if debug:
            return "", {"related_files": [], "referenced_symbols": set(), "signatures": [], "budget": {"used_chars": 0, "max_chars": max_tokens * 4}}
        return ""

    referenced = lc.extract_referenced_symbols(source)

    context_parts = []
    total_len = 0
    char_budget = max_tokens * 4
    sig_details = []

    for rel_file in related:
        try:
            rel_source = rel_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        extends_this = any(rel_file.stem in line for line in source.split("\n") if re.match(r".*\b(?:extends|implements)\b", line))
        filter_symbols = None if extends_this else referenced

        sig = lc.extract_signature(rel_source, rel_file, filter_symbols)
        if not sig:
            continue

        if total_len + len(sig) > char_budget:
            if debug:
                sig_details.append({"file": str(rel_file.name), "sig_length": len(sig), "included": False})
            break

        context_parts.append(sig)
        total_len += len(sig)
        if debug:
            sig_details.append({"file": str(rel_file.name), "sig_length": len(sig), "included": True})

    if not context_parts:
        if debug:
            return "", {"related_files": [str(f.name) for f in related], "referenced_symbols": referenced, "signatures": sig_details, "budget": {"used_chars": 0, "max_chars": char_budget}}
        return ""

    result = "\n\n".join(context_parts) + "\n\n"
    if debug:
        debug_info = {
            "related_files": [str(f.name) for f in related],
            "referenced_symbols": referenced,
            "signatures": sig_details,
            "budget": {"used_chars": total_len, "max_chars": char_budget},
        }
        return result, debug_info
    return result
