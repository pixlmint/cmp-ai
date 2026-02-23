"""Tests for AST span extraction (requires tree-sitter)."""

import random

import pytest

ts = pytest.importorskip("tree_sitter")

from generate._spans_ast import (
    extract_spans_ast,
    _aligned_span_from_random,
    _build_function_prefix_sums,
    _trim_trailing_comments,
)
from fim.deps import Parser


class TestAstSpanExtraction:
    def test_returns_ast_kinds(self, simple_class_php, seed_rng):
        spans = extract_spans_ast(simple_class_php)
        kinds = {s.kind for s in spans}
        assert kinds <= {"ast_single_node", "ast_aligned_span"}
        assert len(kinds) > 0

    def test_count_scales_with_file_size(self, seed_rng):
        small = "<?php\nfunction f() { return 1; }\n"
        big = small + "\n".join(f"function f{i}() {{ return {i}; }}" for i in range(50))
        small_spans = extract_spans_ast(small)
        big_spans = extract_spans_ast(big)
        assert len(big_spans) > len(small_spans)

    def test_single_node_has_valid_byte_offsets(self, simple_class_php, seed_rng):
        spans = extract_spans_ast(simple_class_php)
        source_bytes = simple_class_php.encode("utf-8")
        for span in spans:
            if span.kind == "ast_single_node":
                assert 0 <= span.start_byte < span.end_byte <= len(source_bytes)

    def test_single_node_can_extract_names(self, simple_class_php, seed_rng):
        spans = extract_spans_ast(simple_class_php)
        single_nodes = [s for s in spans if s.kind == "ast_single_node"]
        # Single-node spans exist and some may have names extracted
        assert len(single_nodes) > 0
        # Name extraction depends on which nodes are randomly selected;
        # just verify the name field is always a string
        for s in single_nodes:
            assert isinstance(s.name, str)

    def test_aligned_spans_have_valid_byte_offsets(self, simple_class_php, seed_rng):
        spans = extract_spans_ast(simple_class_php)
        source_bytes = simple_class_php.encode("utf-8")
        for span in spans:
            if span.kind == "ast_aligned_span":
                assert 0 <= span.start_byte < span.end_byte <= len(source_bytes)

    def test_aligned_spans_capped_at_half_source(self, simple_class_php, seed_rng):
        spans = extract_spans_ast(simple_class_php)
        source_len = len(simple_class_php.encode("utf-8"))
        for span in spans:
            if span.kind == "ast_aligned_span":
                span_size = span.end_byte - span.start_byte
                assert span_size <= source_len // 2

    def test_max_middle_lines_filters_long_spans(self, simple_class_php, seed_rng):
        spans_unlimited = extract_spans_ast(simple_class_php, max_middle_lines=0)
        spans_limited = extract_spans_ast(simple_class_php, max_middle_lines=5)
        source_bytes = simple_class_php.encode("utf-8")
        for span in spans_limited:
            if span.kind == "ast_aligned_span":
                line_count = source_bytes[span.start_byte:span.end_byte].count(b"\n") + 1
                assert line_count <= 5


class TestMultiFunctionConstraint:
    """Tests that aligned spans don't span multiple function definitions."""

    MULTI_METHOD_PHP = """\
<?php

class Calculator
{
    // Add two numbers
    public function add(int $a, int $b): int
    {
        return $a + $b;
    }

    // Subtract two numbers
    public function subtract(int $a, int $b): int
    {
        return $a - $b;
    }

    // Multiply two numbers
    public function multiply(int $a, int $b): int
    {
        return $a * $b;
    }

    // Divide two numbers
    public function divide(int $a, int $b): float
    {
        if ($b === 0) {
            throw new \\InvalidArgumentException('Division by zero');
        }
        return $a / $b;
    }
}
"""

    def test_aligned_span_never_spans_multiple_methods(self, seed_rng):
        """No aligned span should contain more than one method_declaration."""
        from fim.language import get_language
        lc = get_language('php')
        source_bytes = self.MULTI_METHOD_PHP.encode('utf-8')
        parser = Parser(lc.ts_language)
        tree = parser.parse(source_bytes)
        root = tree.root_node

        func_types = lc.ast_function_types
        # Run many random selections to exercise the constraint
        for _ in range(200):
            span_len = random.randint(20, max(21, len(source_bytes) // 4))
            max_start = len(source_bytes) - span_len
            if max_start < 1:
                continue
            start = random.randint(1, max_start)
            end = start + span_len

            result = _aligned_span_from_random(source_bytes, root, start, end, function_types=func_types)
            if result is None:
                continue
            s, e = result
            middle = source_bytes[s:e].decode('utf-8', errors='replace')
            # Count how many method declarations appear in the span
            method_count = middle.count('public function ')
            assert method_count <= 1, f"Span contains {method_count} methods:\n{middle}"


class TestTrimTrailingComments:
    """Tests for _trim_trailing_comments helper."""

    def test_trims_trailing_comments(self):
        from fim.language import get_language
        lc = get_language('php')

        source = """\
<?php

class Foo
{
    public function bar(): void
    {
        echo 'bar';
    }

    // This is a trailing comment
    // Another trailing comment
    public function baz(): void
    {
        echo 'baz';
    }
}
"""
        source_bytes = source.encode('utf-8')
        parser = Parser(lc.ts_language)
        tree = parser.parse(source_bytes)
        root = tree.root_node

        # Find the class body node
        class_node = None
        for child in root.children:
            if child.type == 'class_declaration':
                class_node = child
                break
        assert class_node is not None

        # Get the declaration_list (class body)
        body = None
        for child in class_node.children:
            if child.type == 'declaration_list':
                body = child
                break
        assert body is not None

        children = [c for c in body.children if c.end_byte > c.start_byte]
        # Find range that includes comments at the end
        comment_indices = [k for k, c in enumerate(children) if c.type == 'comment']
        if comment_indices:
            # Pick a range ending with a comment
            last_comment_idx = comment_indices[-1]
            first_idx = 0
            trimmed_j = _trim_trailing_comments(children, first_idx, last_comment_idx)
            assert children[trimmed_j].type != 'comment'


class TestCountFunctionChildren:
    """Tests for _count_function_children helper."""

    def test_counts_functions_correctly(self):
        from fim.language import get_language
        lc = get_language('php')

        source = """\
<?php

class Foo
{
    public function bar(): void {}
    public function baz(): void {}
}
"""
        source_bytes = source.encode('utf-8')
        parser = Parser(lc.ts_language)
        tree = parser.parse(source_bytes)
        root = tree.root_node

        # Find the class body
        class_node = None
        for child in root.children:
            if child.type == 'class_declaration':
                class_node = child
                break
        assert class_node is not None

        body = None
        for child in class_node.children:
            if child.type == 'declaration_list':
                body = child
                break
        assert body is not None

        children = [c for c in body.children if c.end_byte > c.start_byte]
        method_children = [k for k, c in enumerate(children) if c.type == 'method_declaration']
        assert len(method_children) >= 2

        prefix = _build_function_prefix_sums(children, lc.ast_function_types)

        # Counting full range should find 2+ functions
        total = prefix[len(children)] - prefix[0]
        assert total >= 2

        # Counting a single method child should find exactly 1
        k = method_children[0]
        count_single = prefix[k + 1] - prefix[k]
        assert count_single == 1
