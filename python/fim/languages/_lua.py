"""Lua language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_lua as tslua
    from tree_sitter import Language

    _ts_language = Language(tslua.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"""require\s*[\(]?\s*['"]([^'"]+)['"]""", source):
        names.add(m.group(1).rsplit('.', 1)[-1])
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

    for line in lines:
        stripped = line.strip()

        m = re.match(r'^(?:local\s+)?function\s+([\w.:]+)\s*\(', stripped)
        if m:
            fn_name = m.group(1).rsplit('.', 1)[-1].rsplit(':', 1)[-1]
            if referenced_symbols is not None and fn_name not in referenced_symbols:
                continue
            sig_lines.append(line.rstrip() + ' ... end')
            continue

        m = re.match(r'^([\w.]+)\s*=\s*function\s*\(', stripped)
        if m:
            fn_name = m.group(1).rsplit('.', 1)[-1]
            if referenced_symbols is not None and fn_name not in referenced_symbols:
                continue
            sig_lines.append(line.rstrip() + ' ... end')

    if not sig_lines:
        return ''
    if len(sig_lines) > max_lines:
        sig_lines = sig_lines[:max_lines]
    header = f'-- --- {filepath.name} ---\n'
    return header + '\n'.join(sig_lines)


def _extract_referenced_symbols(source: str) -> set[str]:
    symbols: set[str] = set()
    for m in re.finditer(r'\b(\w+)\s*\(', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'[.:](\w+)', source):
        symbols.add(m.group(1))
    return symbols


LUA = LanguageConfig(
    name='lua',
    extensions=['.lua'],
    comment_prefix='--',
    skip_dirs=COMMON_SKIP_DIRS | {'luarocks'},
    skip_patterns=[],
    is_test_file=make_test_file_detector('test', 'spec'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'for_in_statement', 'while_statement',
        'repeat_statement', 'function_declaration', 'function_definition',
        'variable_declaration', 'assignment_statement',
        'function_call', 'do_statement', 'local_function',
    }),
    ast_bracket_types={
        'arguments', 'parameters', 'table_constructor',
        'parenthesized_expression',
    },
    ast_ident_node_types={'identifier'},
    ast_name_node_type='identifier',
    regex_func_pattern=r'^(\s*)(?:local\s+)?function\s+([\w.:]+)\s*\(',
    regex_array_pattern=r'^(\s*)\S.*\{\s*$',
    regex_block_keywords='',
    trigger_tokens=[
        'if ', 'elseif ', 'while ', 'for ',
        'return ', '= ', 'function ', 'local ',
        '(', '{', '.',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(LUA)
