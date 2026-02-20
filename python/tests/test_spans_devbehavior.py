"""Tests for developer behavior spans (requires tree-sitter)."""

import pytest

from fim.deps import HAS_TREE_SITTER
from generate._spans_devbehavior import (
    generate_incomplete_line_spans,
    generate_bracket_context_spans,
    generate_post_comment_spans,
)

needs_tree_sitter = pytest.mark.skipif(
    not HAS_TREE_SITTER, reason="tree-sitter not installed"
)


def _parse_tree(source):
    """Parse PHP source and return tree root node."""
    from fim.deps import Parser
    from fim.language import PHP
    parser = Parser(PHP.ts_language)
    tree = parser.parse(source.encode("utf-8"))
    return tree.root_node


class TestIncompleteLineSpans:
    def test_generates_spans_with_byte_offsets(self, simple_class_php, seed_rng):
        spans = generate_incomplete_line_spans(simple_class_php)
        assert len(spans) >= 1
        for span in spans:
            assert span.kind == "dev_incomplete_line"
            assert span.start_byte >= 0
            assert span.end_byte > span.start_byte

    def test_middle_is_rest_of_line(self, simple_class_php, seed_rng):
        spans = generate_incomplete_line_spans(simple_class_php)
        for span in spans:
            middle = simple_class_php[span.start_byte:span.end_byte]
            assert len(middle) >= 3

    def test_works_without_tree(self, simple_class_php, seed_rng):
        """Random-only fallback when tree=None."""
        spans = generate_incomplete_line_spans(simple_class_php, tree=None)
        assert len(spans) >= 1


class TestBracketContentSpans:
    @needs_tree_sitter
    def test_masks_bracket_content(self, class_with_brackets_php, seed_rng):
        tree = _parse_tree(class_with_brackets_php)
        spans = generate_bracket_context_spans(class_with_brackets_php, tree)
        for span in spans:
            assert span.kind == "dev_bracket_content"
            content = class_with_brackets_php[span.start_byte:span.end_byte]
            # Content should not include the delimiters themselves
            assert not content.startswith("[")
            assert not content.startswith("(")

    def test_returns_empty_without_tree(self, class_with_brackets_php):
        spans = generate_bracket_context_spans(class_with_brackets_php, tree=None)
        assert spans == []


class TestPostCommentSpans:
    @needs_tree_sitter
    def test_masks_statement_after_comment(self, class_with_comments_php, seed_rng):
        tree = _parse_tree(class_with_comments_php)
        spans = generate_post_comment_spans(class_with_comments_php, tree)
        assert len(spans) >= 1
        for span in spans:
            assert span.kind == "dev_post_comment"
            middle = class_with_comments_php[span.start_byte:span.end_byte]
            # Middle should be the code after the comment, not the comment itself
            assert not middle.strip().startswith("//")

    def test_returns_empty_without_tree(self, class_with_comments_php):
        spans = generate_post_comment_spans(class_with_comments_php, tree=None)
        assert spans == []
