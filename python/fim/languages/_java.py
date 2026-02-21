"""Java language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, extract_c_family_referenced_symbols, make_brace_signature_extractor, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_java as tsjava
    from tree_sitter import Language

    _ts_language = Language(tsjava.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'^import\s+(?:static\s+)?([\w.]+)\s*;', source, re.MULTILINE):
        names.add(m.group(1).rsplit('.', 1)[-1])
    return names


def _extract_require_files(source: str) -> set[str]:
    return set()


_extract_signature = make_brace_signature_extractor(
    decl_keywords=['class ', 'interface ', 'enum ', 'abstract class', 'public class', 'public interface', 'public enum', '@'],
    func_pattern=r'\s*(?:(?:public|protected|private|static|abstract|final|synchronized|native)\s+)*(?:<[\w<>,?\s]+>\s+)?(?:\w+(?:<[\w<>,?\s]+>)?)\s+(\w+)\s*\(',
    comment_header='//',
    member_pattern=r'(?:(?:public|protected|private|static|final)\s+)*(?:\w+(?:<[\w<>,?\s]+>)?)\s+\w+\s*[=;]',
    private_pattern=r'\bprivate\b',
)

_extract_referenced_symbols = extract_c_family_referenced_symbols

JAVA = LanguageConfig(
    name='java',
    extensions=['.java'],
    comment_prefix='//',
    skip_dirs=COMMON_SKIP_DIRS | {'target', '.gradle', '.mvn', 'bin', 'out'},
    skip_patterns=[r'package-info\.java$', r'module-info\.java$'],
    is_test_file=make_test_file_detector('test', 'tests'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'enhanced_for_statement', 'while_statement',
        'switch_expression', 'try_statement', 'method_declaration',
        'class_declaration', 'local_variable_declaration',
        'assignment_expression', 'method_invocation', 'object_creation_expression',
        'lambda_expression', 'ternary_expression', 'throw_statement',
        'field_declaration',
    }),
    ast_bracket_types={
        'argument_list', 'formal_parameters', 'array_initializer',
        'parenthesized_expression',
    },
    ast_ident_node_types={'identifier'},
    ast_name_node_type='identifier',
    regex_func_pattern=r'^(\s*)(?:(?:public|protected|private|static|abstract|final|synchronized)\s+)*(?:\w+(?:<[\w<>,?\s]+>)?)\s+(\w+)\s*\(',
    regex_array_pattern=r'^(\s*)\S.*[\[\{]\s*$',
    regex_block_keywords='if|else\\s*if|else|for|while|switch|try|catch',
    trigger_tokens=[
        'if (', 'else if (', 'while (', 'for (',
        'return ', '= ', 'new ', '(', '[', '{',
        'throw ', 'this.',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(JAVA)
