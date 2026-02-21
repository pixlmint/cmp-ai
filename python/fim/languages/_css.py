"""CSS and SCSS language configurations."""

from __future__ import annotations

import re
from pathlib import Path

from fim.language import LanguageConfig, register
from fim.languages._shared import COMMON_SKIP_DIRS

_ts_css = None
try:
    import tree_sitter_css as tscss
    from tree_sitter import Language

    _ts_css = Language(tscss.language())
except ImportError:
    pass

_ts_scss = None
try:
    import tree_sitter_scss as tsscss
    from tree_sitter import Language

    _ts_scss = Language(tsscss.language())
except ImportError:
    pass


def _css_extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"""@import\s+['"]([^'"]+)['"]""", source):
        names.add(Path(m.group(1)).stem)
    return names


def _css_extract_require_files(source: str) -> set[str]:
    return set()


def _css_extract_signature(
    source: str,
    filepath: Path,
    referenced_symbols: set[str] | None = None,
    max_lines: int = 40,
) -> str:
    lines = source.split('\n')
    sig_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if re.match(r'^@(?:media|keyframes|font-face|supports)\b', stripped):
            sig_lines.append(line)
            continue

        if re.match(r'^[.#\w\[\*:&>~+]', stripped) and '{' in stripped:
            sig = stripped
            if '{' in sig:
                sig = sig[: sig.index('{')] + '{ ... }'
            sig_lines.append(sig)
            continue

        if re.match(r'^:root\s*\{', stripped):
            sig_lines.append(':root { ... }')

    if not sig_lines:
        return ''
    if len(sig_lines) > max_lines:
        sig_lines = sig_lines[:max_lines]
    header = f'/* --- {filepath.name} --- */\n'
    return header + '\n'.join(sig_lines)


def _css_extract_referenced_symbols(source: str) -> set[str]:
    symbols: set[str] = set()
    for m in re.finditer(r'\.([a-zA-Z][\w-]*)', source):
        symbols.add(m.group(1))
    for m in re.finditer(r'#([a-zA-Z][\w-]*)', source):
        symbols.add(m.group(1))
    return symbols


CSS = LanguageConfig(
    name='css',
    extensions=['.css'],
    comment_prefix='/*',
    skip_dirs=COMMON_SKIP_DIRS,
    skip_patterns=[r'\.min\.css$'],
    ts_language=_ts_css,
    ast_eligible_types=frozenset({
        'rule_set', 'declaration', 'media_statement',
        'keyframes_statement', 'import_statement',
    }),
    ast_bracket_types={'block', 'parenthesized_value'},
    ast_ident_node_types={'identifier', 'class_name', 'id_name'},
    ast_name_node_type='identifier',
    regex_func_pattern='',
    regex_array_pattern='',
    regex_block_keywords='',
    trigger_tokens=['{', ':', ';', '@media', '@keyframes', '.', '#'],
    extract_imports=_css_extract_imports,
    extract_require_files=_css_extract_require_files,
    extract_signature=_css_extract_signature,
    extract_referenced_symbols=_css_extract_referenced_symbols,
)

register(CSS)


def _scss_extract_imports(source: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"""@(?:import|use|forward)\s+['"]([^'"]+)['"]""", source):
        raw = m.group(1)
        stem = Path(raw).stem
        if stem.startswith('_'):
            stem = stem[1:]
        names.add(stem)
    return names


def _scss_extract_signature(
    source: str,
    filepath: Path,
    referenced_symbols: set[str] | None = None,
    max_lines: int = 40,
) -> str:
    lines = source.split('\n')
    sig_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if re.match(r'^\$[\w-]+\s*:', stripped):
            sig_lines.append(line)
            continue

        if re.match(r'^@mixin\s+[\w-]+', stripped):
            sig = line.rstrip()
            if '{' in sig:
                sig = sig[: sig.index('{')] + '{ ... }'
            sig_lines.append(sig)
            continue

        if re.match(r'^@(?:media|keyframes|supports)\b', stripped):
            sig_lines.append(line)
            continue

        if re.match(r'^[.#\w\[\*:&>~+%]', stripped) and '{' in stripped:
            sig = stripped
            if '{' in sig:
                sig = sig[: sig.index('{')] + '{ ... }'
            sig_lines.append(sig)

    if not sig_lines:
        return ''
    if len(sig_lines) > max_lines:
        sig_lines = sig_lines[:max_lines]
    header = f'// --- {filepath.name} ---\n'
    return header + '\n'.join(sig_lines)


SCSS = LanguageConfig(
    name='scss',
    extensions=['.scss', '.sass'],
    comment_prefix='//',
    skip_dirs=COMMON_SKIP_DIRS,
    skip_patterns=[r'\.min\.css$'],
    ts_language=_ts_scss,
    ast_eligible_types=CSS.ast_eligible_types | frozenset({
        'mixin_statement', 'include_statement', 'each_statement',
        'if_statement', 'for_statement',
    }),
    ast_bracket_types=CSS.ast_bracket_types,
    ast_ident_node_types=CSS.ast_ident_node_types,
    ast_name_node_type='identifier',
    regex_func_pattern=r'^(\s*)@mixin\s+([\w-]+)',
    regex_array_pattern='',
    regex_block_keywords='',
    trigger_tokens=['{', ':', ';', '@media', '@mixin', '@include', '$', '.', '#'],
    extract_imports=_scss_extract_imports,
    extract_require_files=_css_extract_require_files,
    extract_signature=_scss_extract_signature,
    extract_referenced_symbols=_css_extract_referenced_symbols,
)

register(SCSS)
