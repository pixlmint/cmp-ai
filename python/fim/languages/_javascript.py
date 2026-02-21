"""JavaScript and TypeScript language configurations."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, extract_c_family_referenced_symbols, make_test_file_detector

_ts_js = None
try:
    import tree_sitter_javascript as tsjs
    from tree_sitter import Language

    _ts_js = Language(tsjs.language())
except ImportError:
    pass

_ts_ts = None
try:
    import tree_sitter_typescript as tsts
    from tree_sitter import Language

    _ts_ts = Language(tsts.language_typescript())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"""(?:import\s+.*?\s+from|require\s*\()\s*['"]([^'"]+)['"]""", source):
        raw = m.group(1)
        names.add(Path(raw).stem if raw.startswith('.') else raw.rsplit('/', 1)[-1])
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

        if stripped.startswith(('export default', 'export type ', 'export interface ')):
            sig_lines.append(line)
            continue

        m = re.match(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*[(<]', stripped)
        if m:
            fn_name = m.group(1)
            is_referenced = referenced_symbols is None or fn_name in referenced_symbols
            if not is_referenced:
                public_unreferenced_indices.append(len(sig_lines))
            sig = line.rstrip()
            if '{' in sig:
                sig = sig[: sig.index('{')] + '{ ... }'
            else:
                sig += ' { ... }'
            sig_lines.append(sig)
            continue

        if re.match(r'^(?:export\s+)?(?:class|interface|type|enum)\s+\w+', stripped):
            sig_lines.append(line)
            continue

        m = re.match(r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*[:=]', stripped)
        if m:
            name = m.group(1)
            if referenced_symbols is not None and name not in referenced_symbols:
                continue
            sig_lines.append(line.rstrip())

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

JAVASCRIPT = LanguageConfig(
    name='javascript',
    extensions=['.js', '.jsx', '.mjs', '.cjs'],
    comment_prefix='//',
    skip_dirs=COMMON_SKIP_DIRS | {'coverage', '.next', '.nuxt'},
    skip_patterns=[r'\.min\.js$', r'bundle\.js$', r'\.config\.js$'],
    is_test_file=make_test_file_detector('test', 'spec', '__tests__'),
    ts_language=_ts_js,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'for_in_statement', 'while_statement',
        'switch_statement', 'try_statement', 'function_declaration',
        'class_declaration', 'variable_declaration', 'assignment_expression',
        'call_expression', 'new_expression', 'arrow_function',
        'template_string', 'ternary_expression', 'spread_element',
        'jsx_element', 'jsx_self_closing_element',
    }),
    ast_bracket_types={
        'arguments', 'formal_parameters', 'array', 'object',
        'parenthesized_expression', 'subscript_expression',
        'template_substitution',
    },
    ast_ident_node_types={'identifier', 'property_identifier'},
    ast_name_node_type='identifier',
    regex_func_pattern=r'^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(',
    regex_array_pattern=r'^(\s*)\S.*[\[\{]\s*$',
    regex_block_keywords='if|else\\s*if|else|for|while|switch|try|catch',
    trigger_tokens=[
        'if (', 'else if (', 'while (', 'for (',
        'return ', '= ', '=>', 'new ', '(', '[', '{',
        'const ', 'let ', 'var ',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(JAVASCRIPT)

TYPESCRIPT = LanguageConfig(
    name='typescript',
    extensions=['.ts', '.tsx'],
    comment_prefix='//',
    skip_dirs=JAVASCRIPT.skip_dirs,
    skip_patterns=[r'\.d\.ts$', r'\.min\.js$'],
    is_test_file=JAVASCRIPT.is_test_file,
    ts_language=_ts_ts,
    ast_eligible_types=JAVASCRIPT.ast_eligible_types | frozenset({
        'type_alias_declaration', 'interface_declaration',
        'enum_declaration', 'type_assertion',
    }),
    ast_bracket_types=JAVASCRIPT.ast_bracket_types | {'type_arguments'},
    ast_ident_node_types=JAVASCRIPT.ast_ident_node_types | {'type_identifier'},
    ast_name_node_type='identifier',
    regex_func_pattern=JAVASCRIPT.regex_func_pattern,
    regex_array_pattern=JAVASCRIPT.regex_array_pattern,
    regex_block_keywords=JAVASCRIPT.regex_block_keywords,
    trigger_tokens=JAVASCRIPT.trigger_tokens + ['interface ', 'type '],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(TYPESCRIPT)
