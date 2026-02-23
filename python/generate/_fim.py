import random
from pathlib import Path

from fim.deps import Parser
from fim.types import CodeSpan, FIMExample, BM25Index, MIN_MIDDLE_WORDS
from ._spans_ast import extract_spans_ast
from ._spans_regex import extract_spans_regex
from ._spans_charlevel import generate_char_level_splits
from ._spans_devbehavior import (
    generate_incomplete_line_spans,
    generate_bracket_context_spans,
    generate_post_comment_spans,
    generate_doc_comment_spans,
)
from fim.crossfile import build_cross_file_context
from fim.bm25 import retrieve_bm25_context

# Target span category ratios (AST-FIM + SynthCoder papers)
TARGET_RATIOS = {"ast": 0.66, "dev": 0.22, "char": 0.12}


def _categorize(kind: str) -> str:
    if kind.startswith("ast_"):
        return "ast"
    if kind.startswith("dev_"):
        return "dev"
    return "char"


def rebalance_examples(examples: list[FIMExample]) -> list[FIMExample]:
    """Downsample overrepresented categories to match target ratios.

    Only downsamples — if a category is underrepresented, keep all of it
    and redistribute its shortfall proportionally to the others.
    """
    if not examples:
        return examples

    # Group by category
    buckets: dict[str, list[FIMExample]] = {"ast": [], "dev": [], "char": []}
    for ex in examples:
        buckets[_categorize(ex.span_kind)].append(ex)

    total = len(examples)

    # Compute raw targets
    raw_targets = {cat: int(total * ratio) for cat, ratio in TARGET_RATIOS.items()}

    # Find categories that are under target (keep all of them)
    # and redistribute their shortfall to over-target categories
    under = {cat: raw_targets[cat] - len(buckets[cat]) for cat in buckets if len(buckets[cat]) < raw_targets[cat]}
    shortfall = sum(max(0, v) for v in under.values())

    # Categories eligible for downsampling
    over_cats = [cat for cat in buckets if len(buckets[cat]) >= raw_targets[cat]]
    over_ratio_sum = sum(TARGET_RATIOS[cat] for cat in over_cats)

    # Distribute shortfall proportionally among over-target categories
    targets: dict[str, int] = {}
    for cat in buckets:
        if cat in under:
            targets[cat] = len(buckets[cat])  # keep all
        else:
            extra = int(shortfall * TARGET_RATIOS[cat] / over_ratio_sum) if over_ratio_sum > 0 else 0
            targets[cat] = raw_targets[cat] + extra

    # Downsample
    result = []
    for cat, items in buckets.items():
        if len(items) <= targets[cat]:
            result.extend(items)
        else:
            result.extend(random.sample(items, targets[cat]))

    return result


def _resolve_lang_config(lang_config):
    if lang_config is None:
        from fim.language import PHP
        return PHP
    return lang_config


def _make_example_from_byte_span(
    source: str,
    span: CodeSpan,
    rel_path: str,
    xf_context: str,
    max_total_chars: int,
    lines: list[str],
    min_words: int = MIN_MIDDLE_WORDS,
) -> FIMExample | None:
    """Create a FIMExample from a span with byte offsets."""
    sb, eb = span.start_byte, span.end_byte
    prefix = source[:sb]
    middle = source[sb:eb]
    suffix = source[eb:]

    if not middle.strip() or len(middle.split()) < min_words:
        return None

    total = len(prefix) + len(middle) + len(suffix) + len(xf_context)
    if total > max_total_chars:
        max_ctx = max_total_chars // 3
        if len(prefix) > max_ctx:
            prefix = prefix[-max_ctx:]
        if len(suffix) > max_ctx:
            suffix = suffix[:max_ctx]
        total = len(prefix) + len(middle) + len(suffix) + len(xf_context)
        if total > max_total_chars:
            return None

    mid_lines = middle.count("\n") + 1
    return FIMExample(
        filepath=rel_path,
        span_kind=span.kind,
        span_name=span.name,
        prefix=prefix,
        middle=middle,
        suffix=suffix,
        cross_file_context=xf_context,
        middle_lines=mid_lines,
        total_lines=len(lines),
        skip_quality_filters=span.skip_quality_filters,
    )


def _make_example_from_line_span(
    source: str,
    span: CodeSpan,
    rel_path: str,
    xf_context: str,
    max_total_chars: int,
    max_middle_lines: int,
    min_middle_lines: int,
    lines: list[str],
) -> FIMExample | None:
    """Create a FIMExample from a span with line numbers."""
    span_lines = span.end_line - span.start_line + 1
    if span_lines < min_middle_lines or span_lines > max_middle_lines:
        return None

    prefix_lines = lines[:span.start_line]
    middle_lines_lst = lines[span.start_line:span.end_line + 1]
    suffix_lines = lines[span.end_line + 1:]

    prefix = "\n".join(prefix_lines)
    middle = "\n".join(middle_lines_lst)
    suffix = "\n".join(suffix_lines)

    if not middle.strip() or len(middle.split()) < MIN_MIDDLE_WORDS:
        return None

    total = len(prefix) + len(middle) + len(suffix) + len(xf_context)
    if total > max_total_chars:
        max_context_lines = 80
        if len(prefix_lines) > max_context_lines:
            prefix = "\n".join(prefix_lines[-max_context_lines:])
        if len(suffix_lines) > max_context_lines:
            suffix = "\n".join(suffix_lines[:max_context_lines])
        total = len(prefix) + len(middle) + len(suffix) + len(xf_context)
        if total > max_total_chars:
            return None

    return FIMExample(
        filepath=rel_path,
        span_kind=span.kind,
        span_name=span.name,
        prefix=prefix + "\n",
        middle=middle,
        suffix="\n" + suffix if suffix else "",
        cross_file_context=xf_context,
        middle_lines=span_lines,
        total_lines=len(lines),
    )


def generate_fim_examples(
    filepath: Path,
    source: str,
    root: Path,
    all_files: list[Path] | None = None,
    cross_file: bool = False,
    max_middle_lines: int = 30,
    min_middle_lines: int = 1,
    max_total_chars: int = 8192,
    use_ast: bool = True,
    bm25_index: BM25Index | None = None,
    lang_config=None,
) -> list[FIMExample]:
    """
    Generate FIM training examples from a single source file.

    Span distribution (per AST-FIM + SynthCoder papers):
      ~66% AST spans (single-node + aligned-span)
      ~22% developer behavior simulation spans
      ~10% random character-level spans

    When use_ast=False or tree-sitter unavailable, falls back to regex spans
    with char-level random splits.
    """
    lc = _resolve_lang_config(lang_config)
    lines = source.split("\n")
    examples = []

    rel_path = str(filepath.relative_to(root)) if root in filepath.parents else str(filepath)

    # Build cross-file context once per file
    xf_context = ""
    if cross_file and all_files:
        xf_context = build_cross_file_context(filepath, all_files, root, source, lang_config=lc)

    # Build BM25 context once per file (not per-span — the query is similar enough)
    bm25_file_ctx = ""
    if bm25_index is not None:
        file_query = source[:2000]
        bm25_file_ctx = retrieve_bm25_context(
            file_query, "", bm25_index, rel_path,
        )

    # Parse tree once for reuse across span generators
    tree_root = None
    if use_ast and lc.ts_language is not None:
        parser = Parser(lc.ts_language)
        tree = parser.parse(source.encode("utf-8"))
        tree_root = tree.root_node

    # --- Collect all spans ---
    all_spans: list[CodeSpan] = []

    if use_ast and lc.ts_language is not None:
        # AST spans (~66% — from extract_spans_ast which has its own count scaling)
        ast_spans = extract_spans_ast(source, lang_config=lc, max_middle_lines=max_middle_lines)
        all_spans.extend(ast_spans)

        # Developer behavior spans (~22%)
        all_spans.extend(generate_incomplete_line_spans(source, tree_root, lang_config=lc))
        all_spans.extend(generate_bracket_context_spans(source, tree_root, lang_config=lc))
        all_spans.extend(generate_post_comment_spans(source, tree_root, lang_config=lc))
        all_spans.extend(generate_doc_comment_spans(source, tree_root, lang_config=lc))
    else:
        # Regex fallback
        all_spans.extend(extract_spans_regex(source, lang_config=lc))

    # Random char-level spans (~10%)
    char_spans = generate_char_level_splits(source)
    all_spans.extend(char_spans)

    # --- Convert spans to FIMExamples ---
    for span in all_spans:
        ex = None
        if span.start_byte >= 0 and span.end_byte > span.start_byte:
            # Byte-offset spans (AST, dev-behavior)
            min_w = 1 if span.kind.startswith("dev_") else MIN_MIDDLE_WORDS
            ex = _make_example_from_byte_span(
                source, span, rel_path, xf_context, max_total_chars, lines,
                min_words=min_w,
            )
        elif span.kind == "char_random":
            # Char-level random spans (offsets stored in start_line/end_line)
            fake_byte_span = CodeSpan(
                kind=span.kind, start_line=span.start_line, end_line=span.end_line,
                name=span.name, start_byte=span.start_line, end_byte=span.end_line,
            )
            ex = _make_example_from_byte_span(
                source, fake_byte_span, rel_path, xf_context, max_total_chars, lines,
            )
        else:
            # Line-level spans (regex fallback)
            ex = _make_example_from_line_span(
                source, span, rel_path, xf_context, max_total_chars,
                max_middle_lines, min_middle_lines, lines,
            )

        if ex is not None:
            # Add cached per-file BM25 context if available
            if bm25_file_ctx:
                combined = bm25_file_ctx + ex.cross_file_context
                total = len(ex.prefix) + len(ex.middle) + len(ex.suffix) + len(combined)
                if total <= max_total_chars:
                    ex.cross_file_context = combined

            examples.append(ex)

    return examples
