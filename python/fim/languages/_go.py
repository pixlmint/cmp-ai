"""Go language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, extract_c_family_referenced_symbols, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_go as tsgo
    from tree_sitter import Language

    _ts_language = Language(tsgo.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'"([\w/.-]+)"', source):
        names.add(m.group(1).rsplit('/', 1)[-1])
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

        m = re.match(r'^func\s+(?:\(\w+\s+\*?(\w+)\)\s+)?(\w+)\s*\(', stripped)
        if m:
            fn_name = m.group(2)
            # In Go, unexported = lowercase first letter
            is_private = fn_name[0].islower()
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

        if re.match(r'^type\s+\w+\s+(?:struct|interface)', stripped):
            sig_lines.append(line)
            continue

        if re.match(r'^var\s+\w+', stripped) or re.match(r'^const\s+\w+', stripped):
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

GO = LanguageConfig(
    name='go',
    extensions=['.go'],
    comment_prefix='//',
    skip_dirs=COMMON_SKIP_DIRS | {'vendor'},
    skip_patterns=[r'_generated\.go$', r'\.pb\.go$'],
    is_test_file=make_test_file_detector('_test.go'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'switch_statement', 'select_statement',
        'function_declaration', 'method_declaration',
        'short_var_declaration', 'assignment_statement',
        'call_expression', 'go_statement', 'defer_statement',
        'type_declaration', 'var_declaration', 'const_declaration',
    }),
    ast_bracket_types={
        'argument_list', 'parameter_list', 'literal_value',
        'parenthesized_expression',
    },
    ast_ident_node_types={'identifier', 'field_identifier', 'type_identifier'},
    ast_name_node_type='identifier',
    regex_func_pattern=r'^(\s*)func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(',
    regex_array_pattern=r'^(\s*)\S.*[\[\{]\s*$',
    regex_block_keywords='if|else\\s*if|else|for|switch|select',
    trigger_tokens=[
        'if ', 'for ', 'switch ', 'select ',
        'return ', ':= ', '= ', 'func ',
        '(', '[', '{', 'go ', 'defer ',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(GO)
