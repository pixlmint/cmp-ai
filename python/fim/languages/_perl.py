"""Perl language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_perl as tsperl
    from tree_sitter import Language

    _ts_language = Language(tsperl.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'^use\s+([\w:]+)', source, re.MULTILINE):
        names.add(m.group(1).rsplit('::', 1)[-1])
    return names


def _extract_require_files(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"""require\s+['"]?([\w:.\/]+)['"]?""", source):
        names.add(Path(m.group(1)).stem)
    return names


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

        m = re.match(r'^sub\s+(\w+)', stripped)
        if m:
            fn_name = m.group(1)
            if referenced_symbols is not None and fn_name not in referenced_symbols:
                continue
            sig = line.rstrip()
            if '{' in sig:
                sig = sig[: sig.index('{')] + '{ ... }'
            else:
                sig += ' { ... }'
            sig_lines.append(sig)

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
    for m in re.finditer(r'->(\w+)', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'\b([A-Z]\w+)', source):
        symbols.add(m.group(1))
    return symbols


PERL = LanguageConfig(
    name='perl',
    extensions=['.pl', '.pm'],
    comment_prefix='#',
    skip_dirs=COMMON_SKIP_DIRS | {'blib', 'local'},
    skip_patterns=[],
    is_test_file=make_test_file_detector('test', 't/'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'foreach_statement', 'while_statement',
        'function_definition', 'assignment', 'call_expression',
        'conditional_expression', 'use_statement',
    }),
    ast_bracket_types={
        'arguments', 'array', 'hash',
        'parenthesized_expression',
    },
    ast_ident_node_types={'identifier'},
    ast_name_node_type='identifier',
    ast_function_types=frozenset({'function_definition'}),
    regex_func_pattern=r'^(\s*)sub\s+(\w+)',
    regex_array_pattern=r'^(\s*)\S.*[\[\{(]\s*$',
    regex_block_keywords='if|elsif|else|for|foreach|while|unless|until',
    trigger_tokens=[
        'if (', 'elsif (', 'while (', 'for (', 'foreach (',
        'return ', '= ', 'my ', 'sub ', '(', '[', '{',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(PERL)
