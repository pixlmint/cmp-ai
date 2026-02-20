import random

from fim.deps import HAS_TREE_SITTER, Parser
from fim.types import CodeSpan


def _resolve_lang_config(lang_config):
    if lang_config is None:
        from fim.language import PHP
        return PHP
    return lang_config


def _collect_eligible_nodes(node: "Node", eligible_types: frozenset[str]) -> list["Node"]:
    """Walk tree and collect named nodes eligible for masking."""
    results = []
    if node.type in eligible_types and node.end_byte - node.start_byte > 5:
        results.append(node)
    for child in node.children:
        results.extend(_collect_eligible_nodes(child, eligible_types))
    return results


def _find_deepest_containing(node: "Node", start: int, end: int) -> "Node":
    """Find deepest AST node whose byte range fully contains [start, end)."""
    for child in node.children:
        if child.start_byte <= start and child.end_byte >= end:
            return _find_deepest_containing(child, start, end)
    return node


def _aligned_span_from_random(
    source_bytes: bytes, tree: "Node", start: int, end: int
) -> tuple[int, int] | None:
    """
    Aligned-Span Masking: snap a random char span to AST boundaries.
    Find the LCA node, then select the contiguous subsequence of its
    children that maximizes IoU with the original span.
    """
    lca = _find_deepest_containing(tree, start, end)
    children = [c for c in lca.children if c.end_byte > c.start_byte]
    if not children:
        return lca.start_byte, lca.end_byte

    # Find contiguous child subsequence maximizing IoU with [start, end)
    best_iou = 0.0
    best_range = (lca.start_byte, lca.end_byte)

    for i in range(len(children)):
        for j in range(i, len(children)):
            s = children[i].start_byte
            e = children[j].end_byte
            intersection = max(0, min(e, end) - max(s, start))
            union = max(e, end) - min(s, start)
            if union == 0:
                continue
            iou = intersection / union
            if iou > best_iou:
                best_iou = iou
                best_range = (s, e)

    return best_range


def extract_spans_ast(source: str, lang_config=None) -> list[CodeSpan]:
    """
    Extract code spans using tree-sitter AST (AST-FIM paper).
    50/50 split between single-node masking and aligned-span masking.
    Returns ~1 span per 500 bytes, with 90% AST / 10% random-char ratio
    applied in generate_fim_examples().
    """
    lc = _resolve_lang_config(lang_config)

    if lc.ts_language is None:
        from ._spans_regex import extract_spans_regex
        return extract_spans_regex(source, lang_config=lc)

    parser = Parser(lc.ts_language)
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    root = tree.root_node

    # Target span count scales with file size
    target_count = max(2, len(source_bytes) // 500)
    ast_count = target_count  # all AST spans; random added separately

    # Split: half single-node, half aligned-span
    single_count = ast_count // 2
    aligned_count = ast_count - single_count

    spans = []

    # --- Single-Node Masking ---
    eligible = _collect_eligible_nodes(root, lc.ast_eligible_types)
    if eligible:
        # Weight by byte size
        weights = [max(1, n.end_byte - n.start_byte) for n in eligible]
        total_w = sum(weights)
        probs = [w / total_w for w in weights]

        chosen = random.choices(eligible, weights=probs, k=min(single_count, len(eligible)))
        for node in chosen:
            start_line = node.start_point[0]
            end_line = node.end_point[0]
            name = ""
            for child in node.children:
                if child.type == lc.ast_name_node_type:
                    name = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                    break
            spans.append(CodeSpan(
                kind="ast_single_node",
                start_line=start_line,
                end_line=end_line,
                name=name,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
            ))

    # --- Aligned-Span Masking ---
    for _ in range(aligned_count):
        # Pick random byte span
        span_len = random.randint(20, max(21, len(source_bytes) // 4))
        max_start = len(source_bytes) - span_len
        if max_start < 1:
            continue
        start = random.randint(1, max_start)
        end = start + span_len

        result = _aligned_span_from_random(source_bytes, root, start, end)
        if result is None:
            continue
        s, e = result
        if e - s < 5 or e - s > len(source_bytes) // 2:
            continue

        start_line = source_bytes[:s].count(b"\n")
        end_line = source_bytes[:e].count(b"\n")
        spans.append(CodeSpan(
            kind="ast_aligned_span",
            start_line=start_line,
            end_line=end_line,
            start_byte=s,
            end_byte=e,
        ))

    return spans
