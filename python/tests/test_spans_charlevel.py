"""Tests for character-level random splits."""

from generate._spans_charlevel import generate_char_level_splits


class TestCharLevelSplits:
    def test_returns_char_random_kind(self, simple_class_php, seed_rng):
        spans = generate_char_level_splits(simple_class_php)
        assert all(s.kind == "char_random" for s in spans)

    def test_count_scales_with_lines(self, seed_rng):
        # ~100 lines → ~5 splits (100 // 20)
        source = "<?php\n" + "\n".join(f"$x{i} = {i};" for i in range(100))
        spans = generate_char_level_splits(source)
        assert len(spans) >= 3

    def test_offsets_are_character_offsets(self, simple_class_php, seed_rng):
        spans = generate_char_level_splits(simple_class_php)
        for span in spans:
            # start_line/end_line hold char offsets for char_random
            assert 0 < span.start_line < span.end_line <= len(simple_class_php)

    def test_middle_within_bounds(self, seed_rng):
        source = "<?php\n" + "x" * 2000 + "\n" * 40
        spans = generate_char_level_splits(source, min_middle_chars=10, max_middle_chars=500)
        for span in spans:
            mid_len = span.end_line - span.start_line
            assert 10 <= mid_len <= 500

    def test_empty_source_returns_empty(self):
        assert generate_char_level_splits("") == []

    def test_short_source_returns_empty(self):
        assert generate_char_level_splits("<?php\n$x=1;") == []

    def test_explicit_num_splits(self, simple_class_php, seed_rng):
        spans = generate_char_level_splits(simple_class_php, num_splits=3)
        assert len(spans) == 3
