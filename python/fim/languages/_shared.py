"""Shared helpers for language configurations."""

from __future__ import annotations

import re
from pathlib import Path

COMMON_SKIP_DIRS = {'.git', '.svn', 'node_modules', 'dist', 'build', '.idea', '.vscode'}


def make_brace_signature_extractor(
    decl_keywords: list[str],
    func_pattern: str,
    comment_header: str,
    member_pattern: str | None = None,
    private_pattern: str | None = None,
):
    """
    Factory for C-family languages that share ``{ ... }`` body stripping.

    *decl_keywords* – line-start keywords kept verbatim (``class``, ``interface``, …).
    *func_pattern* – regex whose group(1) is the function/method name.
    *comment_header* – prefix for the file header line (``//``, ``#``, ``--``).
    *member_pattern* – optional regex for property/const lines to keep.
    *private_pattern* – optional regex to detect private methods; matched methods
      are only included when they appear in *referenced_symbols*, while
      non-matching (public/protected) methods are always included.
    """

    def _extract(
        source: str,
        filepath: Path,
        referenced_symbols: set[str] | None = None,
        max_lines: int = 40,
    ) -> str:
        lines = source.split('\n')
        sig_lines: list[str] = []
        # Track which method sig_lines are public/protected and not in referenced_symbols,
        # so we can drop them first if we exceed max_lines.
        public_unreferenced_indices: list[int] = []

        for line in lines:
            stripped = line.strip()

            if any(stripped.startswith(kw) for kw in decl_keywords):
                sig_lines.append(line)
                continue

            m = re.match(func_pattern, line)
            if m:
                fn_name = m.group(1)
                is_private = private_pattern is not None and re.search(private_pattern, line)
                is_referenced = referenced_symbols is None or fn_name in referenced_symbols

                if is_private and not is_referenced:
                    continue

                sig = line.rstrip()
                if '{' in sig:
                    sig = sig[: sig.index('{')] + '{ ... }'
                elif ';' in sig:
                    pass
                else:
                    sig += ' { ... }'
                if not is_private and not is_referenced:
                    public_unreferenced_indices.append(len(sig_lines))
                sig_lines.append(sig)
                continue

            if member_pattern:
                if re.match(member_pattern, stripped):
                    if referenced_symbols is not None:
                        nm = re.search(r'(\w+)', stripped.split('=')[0].split(':')[0].rsplit(' ', 1)[-1])
                        if nm and nm.group(1) not in referenced_symbols:
                            continue
                    sig_lines.append(line)

        if not sig_lines:
            return ''
        if len(sig_lines) > max_lines:
            # Drop public/protected unreferenced methods first
            for idx in reversed(public_unreferenced_indices):
                if len(sig_lines) <= max_lines:
                    break
                sig_lines.pop(idx)
            if len(sig_lines) > max_lines:
                sig_lines = sig_lines[:max_lines]
        header = f'{comment_header} --- {filepath.name} ---\n'
        return header + '\n'.join(sig_lines)

    return _extract


def extract_c_family_referenced_symbols(source: str) -> set[str]:
    """Generic symbol extraction: function calls and PascalCase identifiers."""
    symbols: set[str] = set()
    for m in re.finditer(r'\b(\w+)\s*\(', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'\b([A-Z]\w+)', source):
        symbols.add(m.group(1))
    return symbols


def make_test_file_detector(*markers: str):
    """Return an is_test_file callable that checks for case-insensitive markers."""

    def _is_test(rel_path: str, fname: str) -> bool:
        lower = rel_path.lower()
        return any(m in lower for m in markers)

    return _is_test


def make_import_stem_extractor(pattern: str, group: int = 1, stem: bool = True):
    """
    Return an extract_imports callable that finds ``pattern`` matches
    and returns the file-stem (or last segment) of each match.
    """

    def _extract(source: str) -> set[str]:
        results: set[str] = set()
        for m in re.finditer(pattern, source):
            raw = m.group(group)
            if stem:
                raw = Path(raw).stem
            results.add(raw.rsplit('.', 1)[-1] if '.' in raw else raw)
        return results

    return _extract
