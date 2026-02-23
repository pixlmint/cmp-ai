"""Swift language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, extract_c_family_referenced_symbols, make_brace_signature_extractor, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_swift as tsswift
    from tree_sitter import Language

    _ts_language = Language(tsswift.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'^import\s+(\w+)', source, re.MULTILINE):
        names.add(m.group(1))
    return names


def _extract_require_files(source: str) -> set[str]:
    return set()


_extract_signature = make_brace_signature_extractor(
    decl_keywords=['class ', 'struct ', 'enum ', 'protocol ', 'extension ', 'public class', 'public struct', 'public enum', 'public protocol', 'open class', '@'],
    func_pattern=r'\s*(?:(?:public|private|internal|fileprivate|open|static|class|override|mutating|@\w+)\s+)*func\s+(\w+)\s*[(<]',
    comment_header='//',
    member_pattern=r'(?:(?:public|private|internal|static|class|let|var)\s+)+\w+\s*[:=]',
    private_pattern=r'\b(?:private|fileprivate)\b',
)

_extract_referenced_symbols = extract_c_family_referenced_symbols

SWIFT = LanguageConfig(
    name='swift',
    extensions=['.swift'],
    comment_prefix='//',
    skip_dirs=COMMON_SKIP_DIRS | {'.build', 'Pods', 'Carthage', 'DerivedData'},
    skip_patterns=[r'Package\.swift$'],
    is_test_file=make_test_file_detector('test', 'tests'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'while_statement', 'switch_statement',
        'function_declaration', 'class_declaration', 'struct_declaration',
        'property_declaration', 'assignment', 'call_expression',
        'closure_expression', 'guard_statement', 'throw_statement',
        'enum_declaration', 'protocol_declaration',
    }),
    ast_bracket_types={
        'call_suffix', 'parameter_clause', 'array_literal',
        'dictionary_literal', 'parenthesized_expression',
        'type_arguments',
    },
    ast_ident_node_types={'simple_identifier'},
    ast_name_node_type='simple_identifier',
    ast_function_types=frozenset({'function_declaration'}),
    regex_func_pattern=r'^(\s*)(?:(?:public|private|internal|fileprivate|open|static|class|override|mutating)\s+)*func\s+(\w+)',
    regex_array_pattern=r'^(\s*)\S.*[\[\{]\s*$',
    regex_block_keywords='if|else\\s*if|else|for|while|switch|guard',
    trigger_tokens=[
        'if ', 'else if ', 'while ', 'for ', 'guard ',
        'return ', '= ', 'let ', 'var ', 'func ',
        '(', '[', '{', 'switch ',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(SWIFT)
