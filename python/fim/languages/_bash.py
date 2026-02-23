"""Bash language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_bash as tsbash
    from tree_sitter import Language

    _ts_language = Language(tsbash.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'(?:source|\.)[ \t]+["\']?([^\s"\']+)', source):
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

        m = re.match(r'^(?:function\s+)?(\w+)\s*\(\s*\)', stripped)
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
            continue

        if re.match(r'^export\s+\w+=', stripped) or re.match(r'^readonly\s+\w+=', stripped):
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
    for m in re.finditer(r'\$\{?(\w+)', source):
        symbols.add(m.group(1))
    return symbols


BASH = LanguageConfig(
    name='bash',
    extensions=['.sh', '.bash'],
    comment_prefix='#',
    skip_dirs=COMMON_SKIP_DIRS,
    skip_patterns=[],
    is_test_file=make_test_file_detector('test', 'tests'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'command', 'if_statement', 'for_statement', 'while_statement',
        'case_statement', 'function_definition', 'pipeline',
        'variable_assignment', 'declaration_command', 'redirected_statement',
        'subshell', 'command_substitution',
    }),
    ast_bracket_types={
        'command_substitution', 'subshell', 'array',
    },
    ast_ident_node_types={'word', 'variable_name'},
    ast_name_node_type='word',
    ast_function_types=frozenset({'function_definition'}),
    regex_func_pattern=r'^(\s*)(?:function\s+)?(\w+)\s*\(\s*\)',
    regex_array_pattern='',
    regex_block_keywords='',
    trigger_tokens=[
        'if ', 'elif ', 'while ', 'for ',
        'case ', 'function ', '= ', 'export ',
        '$(', '${',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(BASH)
