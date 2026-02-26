import math
import re
from collections import Counter

from fim.deps import HAS_TREE_SITTER, Parser
from fim.types import FIMExample

# Matches lines that are import/require/include/use statements.
# Covers all 17 supported languages.
_IMPORT_LINE_RE = re.compile(
    r"^\s*(?:"
    r"require_once|require_relative|include_once|include"
    r"|from\s+\S+\s+import\b"
    r"|import\b"
    r"|using\b"
    r"|use\b"
    r"|extern\s+crate\b"
    r"|load\b"
    r"|#\s*include\b"
    r"|source\b"
    r"|@(?:import|use|forward)\b"
    # JS/TS: const/let/var x = require(...)
    r"|(?:const|let|var)\s+\S+\s*=\s*require\s*\("
    # Bare require(...) call as a statement
    r"|require\s*\("
    r")"
)


def _resolve_lang_config(lang_config):
    if lang_config is None:
        from fim.language import PHP
        return PHP
    return lang_config


def print_dataset_stats(examples: list[FIMExample], rejected: int = 0, rejected_by_kind: dict[str, int] | None = None):
    """Print summary statistics about the generated dataset."""
    if not examples:
        print("  No examples generated!")
        return

    kinds = Counter(ex.span_kind for ex in examples)
    mid_lens = [ex.middle_lines for ex in examples]
    has_xf = sum(1 for ex in examples if ex.cross_file_context)
    complexity_scores = [ex.complexity_score for ex in examples if ex.complexity_score > 0]

    # Categorize span types
    ast_count = sum(c for k, c in kinds.items() if k.startswith("ast_"))
    dev_count = sum(c for k, c in kinds.items() if k.startswith("dev_"))
    random_count = sum(c for k, c in kinds.items() if k in ("char_random", "lines"))
    regex_count = sum(c for k, c in kinds.items() if k in ("function_body", "expression", "block"))
    total = len(examples)

    print(f"\n  Dataset Statistics:")
    print(f"  {'─' * 50}")
    print(f"  Total examples:        {total}")
    if rejected:
        print(f"  Quality-filtered out:  {rejected}")
        if rejected_by_kind:
            for kind, count in sorted(rejected_by_kind.items(), key=lambda x: -x[1]):
                print(f"    {kind:<25} {count:>6}")
    print(f"  Unique files:          {len(set(ex.filepath for ex in examples))}")
    print(f"  With cross-file ctx:   {has_xf}")
    print(f"  Span categories:")
    if ast_count:
        print(f"    AST spans:           {ast_count:>6} ({100*ast_count/total:.1f}%)")
    if regex_count:
        print(f"    Regex spans:         {regex_count:>6} ({100*regex_count/total:.1f}%)")
    if dev_count:
        print(f"    Dev-behavior spans:  {dev_count:>6} ({100*dev_count/total:.1f}%)")
    if random_count:
        print(f"    Random spans:        {random_count:>6} ({100*random_count/total:.1f}%)")
    print(f"  Span types (detailed):")
    for kind, count in kinds.most_common():
        print(f"    {kind:<25} {count:>6}")
    print(f"  Middle section lines:")
    print(f"    min: {min(mid_lens)}, max: {max(mid_lens)}, "
          f"mean: {sum(mid_lens)/len(mid_lens):.1f}, "
          f"median: {sorted(mid_lens)[len(mid_lens)//2]}")
    if complexity_scores:
        print(f"  Complexity scores:")
        print(f"    min: {min(complexity_scores):.2f}, max: {max(complexity_scores):.2f}, "
              f"mean: {sum(complexity_scores)/len(complexity_scores):.2f}")


def compute_complexity_score(source: str, lang_config=None) -> float:
    """
    Compute a complexity score for a source file based on AST identifier density.
    Higher = more complex code (more identifiers per byte).
    """
    lc = _resolve_lang_config(lang_config)

    if lc.ts_language is None:
        # Regex fallback: count identifiers roughly
        idents = re.findall(r"\b[a-zA-Z_]\w*\b", source)
        if not source:
            return 0.0
        return len(idents) / max(1, len(source)) * 100

    parser = Parser(lc.ts_language)
    tree = parser.parse(source.encode("utf-8"))

    ident_count = 0
    ident_node_types = lc.ast_ident_node_types

    def _count_idents(node):
        nonlocal ident_count
        if node.type in ident_node_types:
            ident_count += 1
        for child in node.children:
            _count_idents(child)

    _count_idents(tree.root_node)
    if not source:
        return 0.0
    return ident_count / max(1, len(source)) * 100


def _char_entropy(text: str) -> float:
    """Shannon entropy of characters in text."""
    if not text:
        return 0.0
    freq: dict[str, int] = {}
    for c in text:
        freq[c] = freq.get(c, 0) + 1
    total = len(text)
    return -sum((n / total) * math.log2(n / total) for n in freq.values())


def filter_low_quality_examples(examples: list[FIMExample], min_middle_chars: int = 40) -> tuple[list[FIMExample], list[FIMExample], dict[str, int]]:
    """
    Apply heuristic quality filters. Returns (kept, rejected_examples, rejected_by_kind).

    Filters:
    - Min middle length: middle stripped text < min_middle_chars
    - Import-only: middle completes an import/require/include statement
    - Repetition: middle has >50% duplicate lines
    - Entropy: char entropy of middle < 2.0 bits
    - Comment-only: middle is >80% comments
    - Length ratio: middle is <3% or >80% of total (prefix+middle+suffix)
    """
    kept = []
    rejected_examples: list[FIMExample] = []
    rejected_by_kind: dict[str, int] = {}

    for ex in examples:
        middle = ex.middle
        skip = ex.skip_quality_filters

        # Min middle length check
        if "min_length" not in skip:
            if len(middle.strip()) < min_middle_chars:
                rejected_examples.append(ex)
                rejected_by_kind[ex.span_kind] = rejected_by_kind.get(ex.span_kind, 0) + 1
                continue

        # Import-only check: reconstruct lines from prefix tail + middle + suffix head
        if "import" not in skip:
            prefix_tail = ex.prefix.rsplit("\n", 1)[-1] if ex.prefix else ""
            suffix_head = ex.suffix.split("\n", 1)[0] if ex.suffix else ""
            mid_lines = middle.split("\n")
            # Reconstruct the full lines the middle participates in
            full_lines = []
            for i, ml in enumerate(mid_lines):
                line = ml
                if i == 0:
                    line = prefix_tail + line
                if i == len(mid_lines) - 1:
                    line = line + suffix_head
                full_lines.append(line)
            non_empty = [l for l in full_lines if l.strip()]
            if non_empty and all(_IMPORT_LINE_RE.match(l) for l in non_empty):
                rejected_examples.append(ex)
                rejected_by_kind[ex.span_kind] = rejected_by_kind.get(ex.span_kind, 0) + 1
                continue

        # Repetition check
        if "repetition" not in skip:
            mid_lines = middle.split("\n")
            if len(mid_lines) > 2:
                unique = set(l.strip() for l in mid_lines if l.strip())
                total_non_empty = sum(1 for l in mid_lines if l.strip())
                if total_non_empty > 0 and len(unique) / total_non_empty < 0.5:
                    rejected_examples.append(ex)
                    rejected_by_kind[ex.span_kind] = rejected_by_kind.get(ex.span_kind, 0) + 1
                    continue

        # Entropy check
        if "entropy" not in skip:
            if _char_entropy(middle) < 2.0:
                rejected_examples.append(ex)
                rejected_by_kind[ex.span_kind] = rejected_by_kind.get(ex.span_kind, 0) + 1
                continue

        # Comment-only check
        mid_lines = middle.split("\n")
        if "comment_only" not in skip:
            if mid_lines:
                comment_lines = sum(
                    1 for l in mid_lines
                    if l.strip().startswith(("//", "/*", "*", "#"))
                )
                if comment_lines / max(1, len(mid_lines)) > 0.8:
                    rejected_examples.append(ex)
                    rejected_by_kind[ex.span_kind] = rejected_by_kind.get(ex.span_kind, 0) + 1
                    continue

        # Length ratio check
        if "length_ratio" not in skip:
            total_len = len(ex.prefix) + len(middle) + len(ex.suffix)
            if total_len > 0:
                ratio = len(middle) / total_len
                if ratio < 0.03 or ratio > 0.80:
                    rejected_examples.append(ex)
                    rejected_by_kind[ex.span_kind] = rejected_by_kind.get(ex.span_kind, 0) + 1
                    continue

        kept.append(ex)

    return kept, rejected_examples, rejected_by_kind
