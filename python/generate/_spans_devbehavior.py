import random

from fim.types import CodeSpan
from ._spans_ast import _find_deepest_containing


def _resolve_lang_config(lang_config):
    if lang_config is None:
        from fim.language import PHP
        return PHP
    return lang_config


def generate_incomplete_line_spans(
    source: str, tree: "Node | None" = None, lang_config=None
) -> list[CodeSpan]:
    """
    Generate spans simulating a developer typing mid-line (~15% of spans).
    Two sub-strategies: random intra-line and syntax-aware triggered.
    """
    lc = _resolve_lang_config(lang_config)
    lines = source.split("\n")
    spans = []
    target_count = max(1, len(lines) // 30)

    # Sub-strategy 1: Random intra-line (half)
    for _ in range(target_count // 2 + 1):
        candidates = [
            i for i, l in enumerate(lines)
            if l.strip() and not l.strip().startswith(("//", "/*", "*", "#"))
            and len(l.strip()) > 10
        ]
        if not candidates:
            break
        line_idx = random.choice(candidates)
        line = lines[line_idx]
        stripped = line.lstrip()
        indent_len = len(line) - len(stripped)

        if len(stripped) < 5:
            continue
        offset = random.randint(3, len(stripped) - 1)

        line_start = sum(len(l) + 1 for l in lines[:line_idx])
        cut_byte = line_start + indent_len + offset
        line_end_byte = line_start + len(line)

        if line_end_byte - cut_byte < 3:
            continue

        spans.append(CodeSpan(
            kind="dev_incomplete_line",
            start_line=line_idx,
            end_line=line_idx,
            start_byte=cut_byte,
            end_byte=line_end_byte,
        ))

    # Sub-strategy 2: Syntax-aware triggered (half)
    source_bytes = source.encode("utf-8") if tree else b""
    trigger_tokens = lc.trigger_tokens
    for _ in range(target_count // 2 + 1):
        trigger_candidates = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "/*", "*", "#")):
                continue
            for tok in trigger_tokens:
                pos = stripped.find(tok)
                if pos >= 0:
                    trigger_candidates.append((i, line, tok, pos))
                    break
        if not trigger_candidates:
            break

        line_idx, line, tok, tok_pos_in_stripped = random.choice(trigger_candidates)
        indent_len = len(line) - len(line.lstrip())
        cut_in_line = indent_len + tok_pos_in_stripped + len(tok)
        line_start = sum(len(l) + 1 for l in lines[:line_idx])

        end_byte = line_start + len(line)
        if tree:
            cut_byte_abs = line_start + cut_in_line
            node = _find_deepest_containing(tree, cut_byte_abs, cut_byte_abs + 1)
            if node and node.end_byte > cut_byte_abs:
                end_byte = node.end_byte

        cut_byte = line_start + cut_in_line
        if end_byte - cut_byte < 3:
            continue

        end_line = source_bytes[:end_byte].count(b"\n") if source_bytes else source[:end_byte].count("\n")
        spans.append(CodeSpan(
            kind="dev_incomplete_line",
            start_line=line_idx,
            end_line=end_line,
            start_byte=cut_byte,
            end_byte=end_byte,
        ))

    return spans


def generate_bracket_context_spans(
    source: str, tree: "Node | None" = None, lang_config=None
) -> list[CodeSpan]:
    """
    Generate spans for bracket/paren content (~5% of spans).
    Simulates IDE inserting matching brackets and developer filling in.
    """
    lc = _resolve_lang_config(lang_config)
    spans = []
    if not tree:
        return spans

    bracket_types = lc.ast_bracket_types

    bracket_nodes = []

    def _collect_bracket_nodes(node: "Node"):
        if node.type in bracket_types and node.child_count >= 2:
            inner_size = node.end_byte - node.start_byte
            if 3 < inner_size < 2000:
                bracket_nodes.append(node)
        for child in node.children:
            _collect_bracket_nodes(child)

    _collect_bracket_nodes(tree)
    if not bracket_nodes:
        return spans

    target_count = max(1, len(source.split("\n")) // 60)
    chosen = random.sample(bracket_nodes, min(target_count, len(bracket_nodes)))
    source_bytes = source.encode("utf-8")

    for node in chosen:
        first = node.children[0]
        last = node.children[-1]
        inner_start = first.end_byte
        inner_end = last.start_byte

        if inner_end - inner_start < 2:
            continue

        start_line = source_bytes[:inner_start].count(b"\n")
        end_line = source_bytes[:inner_end].count(b"\n")
        spans.append(CodeSpan(
            kind="dev_bracket_content",
            start_line=start_line,
            end_line=end_line,
            start_byte=inner_start,
            end_byte=inner_end,
        ))

    return spans


def generate_post_comment_spans(
    source: str, tree: "Node | None" = None, lang_config=None
) -> list[CodeSpan]:
    """
    Generate spans where middle = statement after a full-line comment (~3%).
    Teaches model to implement code from comment descriptions.
    """
    spans = []
    if not tree:
        return spans

    source_bytes = source.encode("utf-8")

    def _collect_comment_spans(node: "Node"):
        for i, child in enumerate(node.children):
            if child.type == "comment":
                comment_text = source_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                if comment_text.strip().startswith("//") or comment_text.strip().startswith("/*"):
                    if i + 1 < len(node.children):
                        next_sib = node.children[i + 1]
                        if next_sib.type != "comment" and next_sib.end_byte - next_sib.start_byte > 5:
                            start_line = next_sib.start_point[0]
                            end_line = next_sib.end_point[0]
                            spans.append(CodeSpan(
                                kind="dev_post_comment",
                                start_line=start_line,
                                end_line=end_line,
                                start_byte=next_sib.start_byte,
                                end_byte=next_sib.end_byte,
                            ))
            if child.child_count > 0:
                _collect_comment_spans(child)

    _collect_comment_spans(tree)

    target_count = max(1, len(source.split("\n")) // 100)
    if len(spans) > target_count:
        spans = random.sample(spans, target_count)

    return spans
