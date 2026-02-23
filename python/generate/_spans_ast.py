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


def _count_functions_in_node(node, function_types: frozenset[str]) -> int:
    """Recursively count function-type nodes within a subtree."""
    count = 1 if node.type in function_types else 0
    for child in node.children:
        count += _count_functions_in_node(child, function_types)
    return count


def _build_function_prefix_sums(children: list, function_types: frozenset[str]) -> list[int]:
    """Precompute prefix sums of function counts for O(1) range queries.

    Returns list of length len(children)+1 where prefix[i] = total function
    count in children[0:i]. Range query [i, j] = prefix[j+1] - prefix[i].
    """
    prefix = [0] * (len(children) + 1)
    for k, child in enumerate(children):
        prefix[k + 1] = prefix[k] + _count_functions_in_node(child, function_types)
    return prefix


def _trim_trailing_comments(children: list, i: int, j: int) -> int:
    """Walk backwards from j, skip children whose type is 'comment', return adjusted end index."""
    while j > i and children[j].type == 'comment':
        j -= 1
    return j


def _aligned_span_from_random(
    source_bytes: bytes, tree: "Node", start: int, end: int,
    function_types: frozenset[str] = frozenset(),
) -> tuple[int, int] | None:
    """
    Aligned-Span Masking: snap a random char span to AST boundaries.
    Find the LCA node, then select the contiguous subsequence of its
    children that maximizes IoU with the original span.

    Skips candidate ranges spanning more than 1 function-type child
    when function_types is non-empty. Trims trailing comment children.
    """
    lca = _find_deepest_containing(tree, start, end)
    children = [c for c in lca.children if c.end_byte > c.start_byte]
    if not children:
        return lca.start_byte, lca.end_byte

    # Precompute function counts for O(1) range queries
    func_prefix: list[int] | None = None
    if function_types:
        func_prefix = _build_function_prefix_sums(children, function_types)

    # Find contiguous child subsequence maximizing IoU with [start, end)
    best_iou = 0.0
    best_range = (lca.start_byte, lca.end_byte)
    best_ij: tuple[int, int] | None = None

    for i in range(len(children)):
        for j in range(i, len(children)):
            # Skip multi-function spans (O(1) lookup via prefix sums)
            if func_prefix is not None and func_prefix[j + 1] - func_prefix[i] > 1:
                break  # extending j further only adds more functions
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
                best_ij = (i, j)

    # No valid candidate found — reject if function constraint was active
    if best_ij is None:
        if function_types:
            return None
        return best_range

    # Trim trailing comment children from the selected range
    i, j = best_ij
    j = _trim_trailing_comments(children, i, j)
    return (children[i].start_byte, children[j].end_byte)


def extract_spans_ast(source: str, lang_config=None, max_middle_lines: int = 0) -> list[CodeSpan]:
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

        result = _aligned_span_from_random(source_bytes, root, start, end, function_types=lc.ast_function_types)
        if result is None:
            continue
        s, e = result
        if e - s < 5 or e - s > len(source_bytes) // 2:
            continue
        # Reject spans exceeding line limit early
        if max_middle_lines > 0 and source_bytes[s:e].count(b"\n") + 1 > max_middle_lines:
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
