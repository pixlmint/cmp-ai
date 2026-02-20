import random
import re

from fim.types import CodeSpan


def _resolve_lang_config(lang_config):
    if lang_config is None:
        from fim.language import PHP
        return PHP
    return lang_config


def extract_spans_regex(source: str, lang_config=None) -> list[CodeSpan]:
    """
    Extract meaningful code spans from source using regex.
    Falls back to this when tree-sitter is not available.
    """
    lc = _resolve_lang_config(lang_config)
    lines = source.split("\n")
    spans = []

    # 1. Function/method bodies
    if lc.regex_func_pattern:
        func_pattern = re.compile(lc.regex_func_pattern, re.MULTILINE)
        for match in func_pattern.finditer(source):
            indent = len(match.group(1))
            name = match.group(2)
            start_offset = match.start()
            start_line = source[:start_offset].count("\n")

            brace_pos = source.find("{", match.end())
            if brace_pos == -1:
                continue

            depth = 1
            pos = brace_pos + 1
            while pos < len(source) and depth > 0:
                if source[pos] == "{":
                    depth += 1
                elif source[pos] == "}":
                    depth -= 1
                pos += 1

            end_line = source[:pos].count("\n")
            body_start = source[:brace_pos].count("\n") + 1
            body_end = end_line - 1

            if body_end > body_start + 1:
                spans.append(CodeSpan(
                    kind="function_body",
                    start_line=body_start,
                    end_line=body_end,
                    name=name,
                    indent=indent + 4,
                ))

    # 2. Multi-line expressions: array definitions, chained calls
    if lc.regex_array_pattern:
        array_pattern = re.compile(lc.regex_array_pattern, re.MULTILINE)
        for match in array_pattern.finditer(source):
            start_line = source[:match.start()].count("\n")
            indent = len(match.group(1))

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

    # 3. Block statements (if/else/for/while etc.)
    if lc.regex_block_keywords:
        block_pattern = re.compile(
            r"^(\s*)(?:" + lc.regex_block_keywords + r")" r"\s*(?:\(.*\))?\s*\{\s*$",
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
    if len(lines) > 10:
        for _ in range(len(lines) // 10):
            span_len = random.randint(2, min(8, len(lines) // 4))
            start = random.randint(2, len(lines) - span_len - 2)

            if any(lines[start + k].strip().startswith(("*", "//", "/*", "#")) for k in range(span_len)):
                continue

            indent = len(lines[start]) - len(lines[start].lstrip()) if lines[start].strip() else 4
            spans.append(CodeSpan(
                kind="lines",
                start_line=start,
                end_line=start + span_len - 1,
                indent=indent,
            ))

    return spans
