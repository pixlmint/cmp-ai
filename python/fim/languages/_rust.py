"""Rust language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, extract_c_family_referenced_symbols, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_rust as tsrust
    from tree_sitter import Language

    _ts_language = Language(tsrust.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'^use\s+(?:crate|super|self)?::?([\w:]+)', source, re.MULTILINE):
        names.add(m.group(1).rsplit('::', 1)[-1])
    return names


def _extract_require_files(source: str) -> set[str]:
    return set()


def _extract_signature(
    source: str,
    filepath: Path,
    referenced_symbols: set[str] | None = None,
    max_lines: int = 40,
) -> str:
    lines = source.split('\n')
    sig_lines: list[str] = []
    public_unreferenced_indices: list[int] = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('mod '):
            sig_lines.append(line)
            continue

        m = re.match(r'^(?:pub(?:\([\w:]+\))?\s+)?(?:async\s+)?fn\s+(\w+)', stripped)
        if m:
            fn_name = m.group(1)
            # In Rust, non-pub functions are private
            is_private = not stripped.startswith('pub')
            is_referenced = referenced_symbols is None or fn_name in referenced_symbols

            if is_private and not is_referenced:
                continue

            sig = line.rstrip()
            if '{' in sig:
                sig = sig[: sig.index('{')] + '{ ... }'
            else:
                sig += ' { ... }'
            if not is_private and not is_referenced:
                public_unreferenced_indices.append(len(sig_lines))
            sig_lines.append(sig)
            continue

        if re.match(r'^(?:pub(?:\([\w:]+\))?\s+)?(?:struct|enum|trait|impl|type)\s+\w+', stripped):
            sig_lines.append(line)

    if not sig_lines:
        return ''
    if len(sig_lines) > max_lines:
        for idx in reversed(public_unreferenced_indices):
            if len(sig_lines) <= max_lines:
                break
            sig_lines.pop(idx)
        if len(sig_lines) > max_lines:
            sig_lines = sig_lines[:max_lines]
    header = f'// --- {filepath.name} ---\n'
    return header + '\n'.join(sig_lines)


_extract_referenced_symbols = extract_c_family_referenced_symbols

RUST = LanguageConfig(
    name='rust',
    extensions=['.rs'],
    comment_prefix='//',
    skip_dirs=COMMON_SKIP_DIRS | {'target'},
    skip_patterns=[],
    is_test_file=make_test_file_detector('test', 'tests'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_expression', 'if_expression',
        'for_expression', 'while_expression', 'match_expression',
        'function_item', 'struct_item', 'enum_item', 'impl_item',
        'let_declaration', 'assignment_expression', 'call_expression',
        'macro_invocation', 'closure_expression', 'trait_item',
        'use_declaration',
    }),
    ast_bracket_types={
        'arguments', 'parameters', 'array_expression',
        'parenthesized_expression', 'tuple_expression',
        'type_arguments',
    },
    ast_ident_node_types={'identifier', 'field_identifier', 'type_identifier'},
    ast_name_node_type='identifier',
    ast_function_types=frozenset({'function_item'}),
    regex_func_pattern=r'^(\s*)(?:pub(?:\([\w:]+\))?\s+)?(?:async\s+)?fn\s+(\w+)',
    regex_array_pattern=r'^(\s*)\S.*[\[\{]\s*$',
    regex_block_keywords='if|else\\s*if|else|for|while|match|loop',
    trigger_tokens=[
        'if ', 'else if ', 'while ', 'for ', 'match ',
        'return ', '= ', 'let ', 'fn ', '(', '[', '{',
        '=> ', ':: ',
    ],
    doc_comment_openers=['///'],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(RUST)
