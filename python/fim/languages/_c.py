"""C and C++ language configurations."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, extract_c_family_referenced_symbols, make_test_file_detector

_ts_c = None
try:
    import tree_sitter_c as tsc
    from tree_sitter import Language

    _ts_c = Language(tsc.language())
except ImportError:
    pass

_ts_cpp = None
try:
    import tree_sitter_cpp as tscpp
    from tree_sitter import Language

    _ts_cpp = Language(tscpp.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'#include\s*"([^"]+)"', source):
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

        if re.match(r'^(?:typedef\s+)?(?:struct|union|enum|class|namespace)\s+\w+', stripped):
            sig_lines.append(line)
            continue

        m = re.match(r'^(?:(?:static|inline|extern|virtual|const|unsigned|signed)\s+)*(?:\w+[\s*&]+)+(\w+)\s*\(', stripped)
        if m:
            fn_name = m.group(1)
            if referenced_symbols is not None and fn_name not in referenced_symbols:
                continue
            sig = line.rstrip()
            if '{' in sig:
                sig = sig[: sig.index('{')] + '{ ... }'
            elif sig.endswith(';'):
                pass
            else:
                sig += ';'
            sig_lines.append(sig)

    if not sig_lines:
        return ''
    if len(sig_lines) > max_lines:
        sig_lines = sig_lines[:max_lines]
    header = f'// --- {filepath.name} ---\n'
    return header + '\n'.join(sig_lines)


_extract_referenced_symbols = extract_c_family_referenced_symbols

C = LanguageConfig(
    name='c',
    extensions=['.c', '.h'],
    comment_prefix='//',
    skip_dirs=COMMON_SKIP_DIRS | {'cmake-build-debug', 'cmake-build-release'},
    skip_patterns=[],
    is_test_file=make_test_file_detector('test', 'tests'),
    ts_language=_ts_c,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'while_statement', 'switch_statement',
        'function_definition', 'declaration', 'assignment_expression',
        'call_expression', 'struct_specifier', 'enum_specifier',
        'preproc_if', 'preproc_ifdef', 'compound_statement',
    }),
    ast_bracket_types={
        'argument_list', 'parameter_list', 'initializer_list',
        'parenthesized_expression',
    },
    ast_ident_node_types={'identifier', 'field_identifier', 'type_identifier'},
    ast_name_node_type='identifier',
    ast_function_types=frozenset({'function_definition'}),
    regex_func_pattern=r'^(\s*)(?:(?:static|inline|extern)\s+)*(?:\w+[\s*]+)+(\w+)\s*\(',
    regex_array_pattern=r'^(\s*)\S.*[\[\{]\s*$',
    regex_block_keywords='if|else\\s*if|else|for|while|switch',
    trigger_tokens=[
        'if (', 'else if (', 'while (', 'for (',
        'return ', '= ', '(', '[', '{',
        'sizeof(', 'struct ',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(C)

CPP = LanguageConfig(
    name='cpp',
    extensions=['.cpp', '.cc', '.cxx', '.hpp', '.hxx'],
    comment_prefix='//',
    skip_dirs=C.skip_dirs,
    skip_patterns=[],
    is_test_file=C.is_test_file,
    ts_language=_ts_cpp,
    ast_eligible_types=C.ast_eligible_types | frozenset({
        'class_specifier', 'template_declaration', 'namespace_definition',
        'lambda_expression', 'new_expression', 'throw_statement',
        'try_statement',
    }),
    ast_bracket_types=C.ast_bracket_types | {'template_argument_list'},
    ast_ident_node_types=C.ast_ident_node_types | {'namespace_identifier'},
    ast_name_node_type='identifier',
    ast_function_types=C.ast_function_types,
    regex_func_pattern=C.regex_func_pattern,
    regex_array_pattern=C.regex_array_pattern,
    regex_block_keywords=C.regex_block_keywords + '|try|catch',
    trigger_tokens=C.trigger_tokens + ['new ', 'std::', 'auto ', 'template<'],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(CPP)
