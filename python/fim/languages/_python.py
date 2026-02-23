"""Python language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_python as tspython
    from tree_sitter import Language

    _ts_language = Language(tspython.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'^from\s+([\w.]+)\s+import\b', source, re.MULTILINE):
        names.add(m.group(1).rsplit('.', 1)[-1])
    for m in re.finditer(r'^import\s+([\w.]+)', source, re.MULTILINE):
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
    public_unreferenced_indices: list[int] = []

    for line in lines:
        stripped = line.strip()

        m = re.match(r'^(\s*)(?:async\s+)?def\s+(\w+)\s*\(', line)
        if m:
            fn_name = m.group(2)
            is_private = fn_name.startswith('_')
            is_referenced = referenced_symbols is None or fn_name in referenced_symbols

            if is_private and not is_referenced:
                continue

            if not is_private and not is_referenced:
                public_unreferenced_indices.append(len(sig_lines))
            sig_lines.append(line.rstrip() + ' ...')
            continue

        if re.match(r'^class\s+\w+', stripped):
            sig_lines.append(line)
            continue

        if re.match(r'^\s+\w+\s*:\s*\w+', line) and not stripped.startswith('#'):
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
    header = f'# --- {filepath.name} ---\n'
    return header + '\n'.join(sig_lines)


def _extract_referenced_symbols(source: str) -> set[str]:
    symbols: set[str] = set()
    for m in re.finditer(r'\b(\w+)\s*\(', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'\b([A-Z]\w+)', source):
        symbols.add(m.group(1))
    return symbols


PYTHON = LanguageConfig(
    name='python',
    extensions=['.py'],
    comment_prefix='#',
    skip_dirs=COMMON_SKIP_DIRS | {'__pycache__', '.tox', '.mypy_cache', '.pytest_cache', 'venv', '.venv', 'env', '.eggs', '*.egg-info'},
    skip_patterns=[r'setup\.py$', r'conftest\.py$'],
    is_test_file=make_test_file_detector('test', 'tests'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'while_statement', 'try_statement',
        'function_definition', 'class_definition', 'assignment',
        'augmented_assignment', 'call', 'with_statement',
        'assert_statement', 'raise_statement', 'yield',
        'list_comprehension', 'dictionary_comprehension',
        'set_comprehension', 'generator_expression',
        'conditional_expression', 'lambda', 'decorated_definition',
    }),
    ast_bracket_types={
        'argument_list', 'parameters', 'list', 'dictionary',
        'set', 'tuple', 'parenthesized_expression', 'subscript',
    },
    ast_ident_node_types={'identifier'},
    ast_name_node_type='identifier',
    ast_function_types=frozenset({'function_definition'}),
    regex_func_pattern=r'^(\s*)(?:async\s+)?def\s+(\w+)\s*\(',
    regex_array_pattern=r'^(\s*)\S.*[\[\{]\s*$',
    regex_block_keywords='',
    trigger_tokens=[
        'if ', 'elif ', 'while ', 'for ', 'return ',
        '= ', 'def ', 'class ', 'with ', 'import ',
        '(', '[', '{',
    ],
    doc_comment_openers=['"""', "'''"],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(PYTHON)
