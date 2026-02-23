"""
Language configuration abstraction for multi-language FIM support.

Each language bundles all language-specific behavior into a single LanguageConfig
dataclass. A module-level registry maps language names to configs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# LanguageConfig dataclass
# ---------------------------------------------------------------------------


@dataclass
class LanguageConfig:
    name: str  # "php"
    extensions: list[str]  # [".php"]
    comment_prefix: str  # "//"

    # File discovery
    skip_dirs: set[str] = field(default_factory=set)
    skip_patterns: list[str] = field(default_factory=list)  # regex patterns
    is_test_file: Callable[[str, str], bool] = field(default=lambda rel_path, fname: False)

    # Tree-sitter (None if grammar not installed)
    ts_language: object | None = None

    # AST span config
    ast_eligible_types: frozenset[str] = field(default_factory=frozenset)
    ast_bracket_types: set[str] = field(default_factory=set)
    ast_ident_node_types: set[str] = field(default_factory=set)
    ast_name_node_type: str = "name"  # "name" for PHP, "identifier" for Python
    ast_function_types: frozenset[str] = field(default_factory=frozenset)

    # Regex fallback spans
    regex_func_pattern: str = ""
    regex_array_pattern: str = ""
    regex_block_keywords: str = ""  # pipe-separated

    # Dev-behavior spans
    trigger_tokens: list[str] = field(default_factory=list)

    # Cross-file context (callables — logic differs too much per language)
    extract_imports: Callable[[str], set[str]] = field(default=lambda source: set())
    extract_require_files: Callable[[str], set[str]] = field(default=lambda source: set())
    extract_signature: Callable[[str, Path, set[str] | None, int], str] = field(default=lambda source, filepath, referenced_symbols, max_lines: "")
    extract_referenced_symbols: Callable[[str], set[str]] = field(default=lambda source: set())


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, LanguageConfig] = {}


def register(config: LanguageConfig) -> None:
    _REGISTRY[config.name] = config


def get_language(name: str) -> LanguageConfig:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown language: {name!r}. Registered: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]


def registered_languages() -> list[str]:
    return list(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Import all language modules to trigger registration
# ---------------------------------------------------------------------------

import fim.languages  # noqa: E402, F401

# Backward compatibility: re-export PHP constant
from fim.languages._php import PHP  # noqa: E402, F401
