"""PHP language configuration."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fim.language import LanguageConfig, register

_ts_language = None
try:
    import tree_sitter_php as tsphp
    from tree_sitter import Language

    _ts_language = Language(tsphp.language_php())
except ImportError:
    pass


def _extract_imports(source: str) -> set[str]:
    """Extract class names from PHP ``use`` statements."""
    classes = set()
    for match in re.finditer(r'use\s+([\w\\]+?)(?:\s+as\s+\w+)?;', source):
        fqcn = match.group(1)
        classes.add(fqcn.split('\\')[-1])
    return classes


def _extract_require_files(source: str) -> set[str]:
    """Extract filenames from PHP require/include statements."""
    files = set()
    for match in re.finditer(r"(?:require|include)(?:_once)?\s*\(\s*['\"]([^'\"]+?)['\"]\s*\)", source):
        file_path = match.group(1)
        filename = os.path.basename(file_path)
        filename = os.path.splitext(filename)[0]
        files.add(filename)
    return files


def _extract_signature(
    source: str,
    filepath: Path,
    referenced_symbols: set[str] | None = None,
    max_lines: int = 40,
) -> str:
    """
    Extract a compact signature of a PHP file: namespace, use statements,
    class declaration, and method signatures (without bodies).
    """
    lines = source.split('\n')
    sig_lines = []

    # Track public/protected unreferenced method indices for overflow pruning
    public_unreferenced_indices: list[int] = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith(('class ', 'interface ', 'trait ', 'abstract class', 'final class', 'enum ')):
            sig_lines.append(line)
            continue

        m = re.match(r'\s*(?:(?:public|protected|private|static|abstract|final)\s+)*' r'function\s+(\w+)\s*\(', line)
        if m:
            method_name = m.group(1)
            is_private = re.search(r'\bprivate\b', line) is not None
            is_referenced = referenced_symbols is None or method_name in referenced_symbols

            if is_private and not is_referenced:
                continue

            sig = line.rstrip()
            if '{' in sig:
                sig = sig[: sig.index('{')] + '{ ... }'
            elif ';' in sig:
                pass
            else:
                sig += ' { ... }'
            if not is_private and not is_referenced:
                public_unreferenced_indices.append(len(sig_lines))
            sig_lines.append(sig)
            continue

        if re.match(r'\s*(?:(?:public|protected|private|static)\s+)*' r'(?:const |(?:\?\w+|\w+) \$)', stripped):
            if referenced_symbols is not None:
                cm = re.search(r'const\s+(\w+)', stripped)
                pm = re.search(r'\$(\w+)', stripped)
                name = (cm.group(1) if cm else None) or (pm.group(1) if pm else None)
                if name and name not in referenced_symbols:
                    continue
            sig_lines.append(line)

    if not sig_lines:
        return ''

    if len(sig_lines) > max_lines:
        # Drop public/protected unreferenced methods first
        for idx in reversed(public_unreferenced_indices):
            if len(sig_lines) <= max_lines:
                break
            sig_lines.pop(idx)
        if len(sig_lines) > max_lines:
            sig_lines = sig_lines[:max_lines]

    header = f'// --- {filepath.name} ---\n'
    return header + '\n'.join(sig_lines)


def _extract_referenced_symbols(source: str) -> set[str]:
    """Extract identifiers referenced in a PHP source file."""
    symbols = set()
    for m in re.finditer(r'(?:->|::)(\w+)\s*\(', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'::(\w+)', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'(?:extends|implements|new|instanceof)\s+(\w+)', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'\b(\w+)\s*\(', source):
        symbols.add(m.group(1))
    return symbols


def _is_test_file(rel_path: str, fname: str) -> bool:
    return 'test' in rel_path.lower() or 'Test' in fname


PHP = LanguageConfig(
    name='php',
    extensions=['.php'],
    comment_prefix='//',
    skip_dirs={'vendor', 'node_modules', '.git', '.svn', 'cache', 'storage', 'public', 'dist', 'build', '.idea', '.vscode'},
    skip_patterns=[
        r'\.blade\.php$',
        r'\.min\.php$',
        r'config/.*\.php$',
        r'database/migrations',
        r'routes/.*\.php$',
    ],
    is_test_file=_is_test_file,
    ts_language=_ts_language,
    ast_eligible_types=frozenset({
        'expression_statement', 'return_statement', 'if_statement',
        'for_statement', 'foreach_statement', 'while_statement',
        'switch_statement', 'try_statement', 'function_definition',
        'method_declaration', 'class_declaration', 'assignment_expression',
        'function_call_expression', 'member_call_expression',
        'object_creation_expression', 'array_creation_expression',
        'match_expression', 'arrow_function', 'anonymous_function',
        'compound_statement', 'argument', 'formal_parameters',
        'property_declaration', 'const_declaration', 'echo_statement',
        'throw_expression', 'yield_expression', 'binary_expression',
        'conditional_expression', 'subscript_expression', 'cast_expression',
    }),
    ast_bracket_types={
        'arguments', 'formal_parameters', 'array_creation_expression',
        'parenthesized_expression', 'subscript_expression',
    },
    ast_ident_node_types={'name', 'variable_name', 'member_access_expression'},
    ast_name_node_type='name',
    regex_func_pattern=r'^(\s*)(?:(?:public|protected|private|static|abstract|final)\s+)*function\s+(\w+)\s*\(',
    regex_array_pattern=r'^(\s*)\S.*(?:\[|array\()\s*$',
    regex_block_keywords='if|else\\s*if|elseif|else|foreach|for|while|switch|try|catch',
    trigger_tokens=[
        'if (', 'elseif (', 'while (', 'for (', 'foreach (',
        'return ', '= ', '=> ', '-> ', '::', 'new ', '(', '[',
        'match (', 'fn(',
    ],
    extract_imports=_extract_imports,
    extract_require_files=_extract_require_files,
    extract_signature=_extract_signature,
    extract_referenced_symbols=_extract_referenced_symbols,
)

register(PHP)
