# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FIM dataset generator and context server for PHP codebases. Used for LoRA fine-tuning of code completion models (Qwen2.5-Coder, Granite-Code, CodeLlama, StarCoder) and providing real-time cross-file context to editor plugins.

Three packages share a common library:
- **`fim/`** — Shared library: types, file discovery, cross-file context, BM25 retrieval
- **`generate/`** — CLI tool: builds FIM training datasets (`python -m generate`)
- **`fimserver/`** — JSON-RPC 2.0 server: provides cross-file context over stdin/stdout (`python -m fimserver`)

## Commands

```bash
# Tests (87 tests, ~0.3s)
make test
venv/bin/python -m pytest tests/ -v                # all tests
venv/bin/python -m pytest tests/test_bm25.py -v    # single file
venv/bin/python -m pytest tests/test_bm25.py::TestTokenizeCode::test_lowercases -v  # single test

# Dataset generation
venv/bin/python -m generate /path/to/php/project --output dataset/ --base-model qwen2.5-coder
venv/bin/python -m generate /path/to/project --preview 5   # dry run

# Context server
make serve
venv/bin/python -m fimserver --log-level DEBUG
```

Uses venv at `./venv`. Makefile `generate-v2` through `generate-v5` targets use hardcoded external paths.

## Architecture

### Package structure and imports

`fim/` is the shared foundation — all public API, no `_` prefix on modules:
- `types.py` — `FIMConfig`, `CodeSpan`, `FIMExample`, `BM25Index`, `FIM_CONFIGS`
- `deps.py` — optional dependency detection (`HAS_TREE_SITTER`, `HAS_BM25`) with graceful fallback
- `discovery.py` — `find_php_files()` with skip rules for vendor/config/templates
- `crossfile.py` — dependency-based signature extraction and cross-file context building
- `bm25.py` — BM25 index construction and retrieval

`generate/` and `fimserver/` both import from `fim.*`. Within `generate/`, private modules use relative imports to each other (e.g., `from ._spans_ast import ...`) but absolute imports to `fim` (e.g., `from fim.types import ...`).

### Dataset generation pipeline

Entry point: `generate/__main__.py` → `generate/_cli.py:main()`

1. `fim.discovery.find_php_files()` discovers PHP files
2. `fim.bm25.build_bm25_index()` builds BM25 index (optional)
3. Per file, `generate/_fim.py:generate_fim_examples()` orchestrates:
   - Builds cross-file context via `fim.crossfile.build_cross_file_context()`
   - Collects `CodeSpan`s from multiple span generators
   - Converts spans to `FIMExample`s
4. `generate/_quality.py` applies post-processing (quality filter, curriculum sort)
5. Output: `train.jsonl` + `val.jsonl` + `metadata.json` (90/10 split, seed 42)

### Span generators

| Module | Span types | Weight | Notes |
|---|---|---|---|
| `_spans_ast.py` | `ast_single_node`, `ast_aligned_span` | ~66% | Requires tree-sitter; masks AST nodes or snaps random spans to AST boundaries |
| `_spans_devbehavior.py` | `dev_incomplete_line`, `dev_bracket_content`, `dev_post_comment` | ~22% | Simulates developer typing patterns; requires tree-sitter for bracket/comment spans |
| `_spans_charlevel.py` | `char_random` | ~10% | Character-level random splits (byte offsets stored in start_line/end_line fields) |
| `_spans_regex.py` | `function_body`, `expression`, `block`, `lines` | fallback | Used when tree-sitter unavailable |

Target: ~1 span per 500 bytes. Generators return `list[CodeSpan]`; conversion to `FIMExample` happens in `_fim.py` via `_make_example_from_byte_span()` or `_make_example_from_line_span()`.

### Cross-file context

1. Parse PHP `use`/`require`/`include` to find dependencies
2. Extract signatures (namespace, class, method declarations) from related files
3. Filter to only symbols referenced in the target file
4. Budget: 1024 tokens (~4096 chars), top 5 files
5. BM25: chunks files on blank lines (max 20 lines), retrieves top-5 from different files

### Context server protocol

`fimserver/_server.py` reads newline-delimited JSON-RPC 2.0 from stdin, writes responses to stdout. `fimserver/_handler.py` manages `ProjectState` (file list, BM25 index, signature cache with mtime invalidation).

Methods: `initialize` (discovers files, builds index), `getContext` (returns cross-file context string), `shutdown` (clean exit).

## Dependencies

Optional deps auto-detected in `fim/deps.py` with graceful fallback:
- `tree-sitter` + `tree-sitter-php` — AST-aware spans (falls back to regex)
- `rank-bm25` — BM25 cross-file retrieval (skipped if missing)
- `tqdm` — always required

## Conventions

- `fim/` modules are public API (no `_` prefix); `generate/` and `fimserver/` private modules use `_` prefix
- Span generators return `list[CodeSpan]`; only `_fim.py` creates `FIMExample`s
- Quality filters: repetition, entropy, comment-only, length ratio checks
- Tests mirror source modules (e.g., `test_bm25.py` tests `fim/bm25.py`, `test_spans_ast.py` tests `generate/_spans_ast.py`)
- Shared fixtures in `tests/conftest.py` — PHP source snippets and `make_example()` helper
