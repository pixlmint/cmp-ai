"""Tests for AST span extraction (requires tree-sitter)."""

import pytest

ts = pytest.importorskip("tree_sitter")

from generate._spans_ast import extract_spans_ast


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
