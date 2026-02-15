"""Tests for regex fallback span extraction (no optional deps needed)."""

from generate._spans_regex import extract_spans_regex
from fim.types import CodeSpan


class TestFunctionBodySpans:
    def test_finds_function_by_name(self, simple_class_php):
        spans = extract_spans_regex(simple_class_php)
        func_spans = [s for s in spans if s.kind == "function_body"]
        names = [s.name for s in func_spans]
        assert "findActive" in names or "deactivate" in names

    def test_body_excludes_braces(self, simple_class_php):
        spans = extract_spans_regex(simple_class_php)
        lines = simple_class_php.split("\n")
        for span in spans:
            if span.kind == "function_body":
                body = "\n".join(lines[span.start_line:span.end_line + 1])
                # The body span itself shouldn't start/end with lone braces
                assert not body.strip().startswith("{")
                assert not body.strip().endswith("}")


class TestBlockSpans:
    def test_finds_block_spans(self, simple_class_php):
        """The foreach/if in findActive() should produce block spans."""
        spans = extract_spans_regex(simple_class_php)
        block_spans = [s for s in spans if s.kind == "block"]
        # The fixture has a foreach with an if inside
        assert len(block_spans) >= 1


class TestRandomLineSpans:
    def test_generates_random_line_spans(self, simple_class_php, seed_rng):
        spans = extract_spans_regex(simple_class_php)
        line_spans = [s for s in spans if s.kind == "lines"]
        # ~35 lines / 10 = ~3 attempts (some may be filtered for comments)
        assert len(line_spans) >= 1

    def test_skips_comment_lines(self, class_with_comments_php, seed_rng):
        spans = extract_spans_regex(class_with_comments_php)
        lines = class_with_comments_php.split("\n")
        for span in spans:
            if span.kind == "lines":
                span_lines = lines[span.start_line:span.end_line + 1]
                for line in span_lines:
                    s = line.strip()
                    assert not s.startswith(("//", "/*", "*", "#"))


class TestSpanValidity:
    def test_all_spans_have_valid_line_numbers(self, simple_class_php, seed_rng):
        spans = extract_spans_regex(simple_class_php)
        num_lines = len(simple_class_php.split("\n"))
        for span in spans:
            assert isinstance(span, CodeSpan)
            assert 0 <= span.start_line <= span.end_line < num_lines
