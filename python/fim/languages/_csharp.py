"""C# language configuration."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS, extract_c_family_referenced_symbols, make_brace_signature_extractor, make_test_file_detector

_ts_language = None
try:
    import tree_sitter_c_sharp as tscsharp
    from tree_sitter import Language

    _ts_language = Language(tscsharp.language())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r'^using\s+(?:static\s+)?([\w.]+)\s*;', source, re.MULTILINE):
        names.add(m.group(1).rsplit('.', 1)[-1])
    return names


def _extract_require_files(source: str) -> set[str]:
    return set()


_extract_signature = make_brace_signature_extractor(
    decl_keywords=['namespace ', 'class ', 'interface ', 'struct ', 'enum ', 'abstract class', 'public class', 'public interface', 'public struct', 'internal class', 'record '],
    func_pattern=r'\s*(?:(?:public|protected|private|internal|static|abstract|virtual|override|async|sealed|partial)\s+)*(?:\w+(?:<[\w<>,?\s]+>)?(?:\[\])?)\s+(\w+)\s*[(<]',
    comment_header='//',
    member_pattern=r'(?:(?:public|protected|private|internal|static|readonly|const)\s+)+\w+(?:<[\w<>,?\s]+>)?\s+\w+\s*[{=;]',
    private_pattern=r'\bprivate\b',
)

_extract_referenced_symbols = extract_c_family_referenced_symbols

CSHARP = LanguageConfig(
    name='csharp',
    extensions=['.cs'],
    comment_prefix='//',
    skip_dirs=COMMON_SKIP_DIRS | {'bin', 'obj', '.vs', 'packages'},
    skip_patterns=[r'\.Designer\.cs$', r'\.g\.cs$', r'AssemblyInfo\.cs$'],
    is_test_file=make_test_file_detector('test', 'tests'),
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'foreach_statement', 'while_statement',
        'switch_statement', 'try_statement', 'method_declaration',
        'class_declaration', 'local_declaration_statement',
        'assignment_expression', 'invocation_expression',
        'object_creation_expression', 'lambda_expression',
        'throw_statement', 'property_declaration',
    }),
    ast_bracket_types={
        'argument_list', 'parameter_list', 'initializer_expression',
        'parenthesized_expression',
    },
    ast_ident_node_types={'identifier'},
    ast_name_node_type='identifier',
    ast_function_types=frozenset({'method_declaration', 'constructor_declaration', 'lambda_expression'}),
    regex_func_pattern=r'^(\s*)(?:(?:public|protected|private|internal|static|abstract|virtual|override|async)\s+)*(?:\w+(?:<[\w<>,?\s]+>)?)\s+(\w+)\s*\(',
    regex_array_pattern=r'^(\s*)\S.*[\[\{]\s*$',
    regex_block_keywords='if|else\\s*if|else|for|foreach|while|switch|try|catch',
    trigger_tokens=[
        'if (', 'else if (', 'while (', 'for (', 'foreach (',
        'return ', '= ', 'new ', '(', '[', '{',
        'var ', 'await ', 'throw ',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(CSHARP)
