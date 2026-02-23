"""Ruby language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_ruby as tsruby
    from tree_sitter import Language

    _ts_language = Language(tsruby.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"""require(?:_relative)?\s+['"]([^'"]+)['"]""", source):
        names.add(Path(m.group(1)).stem)
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

        if re.match(r'^(?:module|class)\s+\w+', stripped):
            sig_lines.append(line)
            continue

        m = re.match(r'^(?:def\s+(?:self\.)?)?(\w+[?!=]?)\s*(?:\(|$)', stripped)
        if m and stripped.startswith('def '):
            fn_name = m.group(1)
            if referenced_symbols is not None and fn_name not in referenced_symbols:
                continue
            sig_lines.append(line.rstrip() + ' ... end')
            continue

        if re.match(r'^attr_(?:reader|writer|accessor)\b', stripped):
            sig_lines.append(line)
            continue

        if re.match(r'^(?:CONSTANT|[A-Z_]+)\s*=', stripped):
            sig_lines.append(line)

    if not sig_lines:
        return ''
    if len(sig_lines) > max_lines:
        sig_lines = sig_lines[:max_lines]
    header = f'# --- {filepath.name} ---\n'
    return header + '\n'.join(sig_lines)


def _extract_referenced_symbols(source: str) -> set[str]:
    symbols: set[str] = set()
    for m in re.finditer(r'\b(\w+)\s*\(', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'\.(\w+[?!=]?)', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'\b([A-Z]\w+)', source):
        symbols.add(m.group(1))
    return symbols


RUBY = LanguageConfig(
    name='ruby',
    extensions=['.rb'],
    comment_prefix='#',
    skip_dirs=COMMON_SKIP_DIRS | {'vendor', 'tmp', 'log'},
    skip_patterns=[r'Gemfile$', r'Rakefile$'],
    is_test_file=make_test_file_detector('test', 'spec'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return', 'if', 'unless',
        'for', 'while', 'until', 'case',
        'method', 'singleton_method', 'class', 'module',
        'assignment', 'call', 'command_call',
        'block', 'do_block', 'lambda', 'begin',
    }),
    ast_bracket_types={
        'argument_list', 'method_parameters', 'array',
        'hash', 'parenthesized_statements',
    },
    ast_ident_node_types={'identifier', 'constant'},
    ast_name_node_type='identifier',
    ast_function_types=frozenset({'method', 'singleton_method'}),
    regex_func_pattern=r'^(\s*)def\s+(?:self\.)?(\w+[?!=]?)',
    regex_array_pattern=r'^(\s*)\S.*[\[\{]\s*$',
    regex_block_keywords='',
    trigger_tokens=[
        'if ', 'elsif ', 'unless ', 'while ', 'until ',
        'return ', '= ', 'def ', 'class ', 'module ',
        '(', '[', '{', 'do', '|',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(RUBY)
