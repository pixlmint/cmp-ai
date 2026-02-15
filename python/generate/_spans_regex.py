import random
import re

from fim.types import CodeSpan


def extract_spans_regex(source: str) -> list[CodeSpan]:
    """
    Extract meaningful code spans from PHP source using regex.
    Falls back to this when tree-sitter is not available.
    """
    lines = source.split("\n")
    spans = []

    # 1. Function/method bodies
    # Match function declarations and find their body via brace counting
    func_pattern = re.compile(
        r"^(\s*)(?:(?:public|protected|private|static|abstract|final)\s+)*"
        r"function\s+(\w+)\s*\(",
        re.MULTILINE,
    )
    for match in func_pattern.finditer(source):
        indent = len(match.group(1))
        name = match.group(2)
        start_offset = match.start()
        start_line = source[:start_offset].count("\n")

        # Find the opening brace
        brace_pos = source.find("{", match.end())
        if brace_pos == -1:
            continue

        # Count braces to find the end
        depth = 1
        pos = brace_pos + 1
        while pos < len(source) and depth > 0:
            if source[pos] == "{":
                depth += 1
            elif source[pos] == "}":
                depth -= 1
            pos += 1

        end_line = source[:pos].count("\n")

        # The "body" is everything between { and }
        body_start = source[:brace_pos].count("\n") + 1
        body_end = end_line - 1

        if body_end > body_start + 1:  # at least 2 lines
            spans.append(CodeSpan(
                kind="function_body",
                start_line=body_start,
                end_line=body_end,
                name=name,
                indent=indent + 4,
            ))

    # 2. Multi-line expressions: array definitions, chained calls
    # Look for = [...] or => [...] spanning multiple lines
    array_pattern = re.compile(r"^(\s*)\S.*(?:\[|array\()\s*$", re.MULTILINE)
    for match in array_pattern.finditer(source):
        start_line = source[:match.start()].count("\n")
        indent = len(match.group(1))

        # Find closing bracket
        depth = 1
        pos = match.end()
        while pos < len(source) and depth > 0:
            if source[pos] in "[({":
                depth += 1
            elif source[pos] in "])}":
                depth -= 1
            pos += 1

        end_line = source[:pos].count("\n")
        if end_line > start_line + 2:
            spans.append(CodeSpan(
                kind="expression",
                start_line=start_line + 1,
                end_line=end_line - 1,
                indent=indent + 4,
            ))

    # 3. If/else/foreach/for/while blocks (just the body)
    block_pattern = re.compile(
        r"^(\s*)(?:if|else\s*if|elseif|else|foreach|for|while|switch|try|catch)"
        r"\s*(?:\(.*\))?\s*\{\s*$",
        re.MULTILINE,
    )
    for match in block_pattern.finditer(source):
        start_line = source[:match.start()].count("\n")
        indent = len(match.group(1))
        brace_pos = match.end() - 1

        depth = 1
        pos = brace_pos + 1
        while pos < len(source) and depth > 0:
            if source[pos] == "{":
                depth += 1
            elif source[pos] == "}":
                depth -= 1
            pos += 1

        end_line = source[:pos].count("\n")
        body_start = start_line + 1
        body_end = end_line - 1

        if body_end > body_start + 1:
            spans.append(CodeSpan(
                kind="block",
                start_line=body_start,
                end_line=body_end,
                indent=indent + 4,
            ))

    # 4. Random contiguous line spans (to teach general patterns)
    # These catch things the structural patterns miss
    if len(lines) > 10:
        for _ in range(len(lines) // 10):  # ~1 per 10 lines
            span_len = random.randint(2, min(8, len(lines) // 4))
            start = random.randint(2, len(lines) - span_len - 2)

            # Don't start/end mid-string or comment
            if any(lines[start + k].strip().startswith(("*", "//", "/*", "#"))
                   for k in range(span_len)):
                continue

            indent = len(lines[start]) - len(lines[start].lstrip()) if lines[start].strip() else 4
            spans.append(CodeSpan(
                kind="lines",
                start_line=start,
                end_line=start + span_len - 1,
                indent=indent,
            ))

    return spans
