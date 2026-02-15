"""End-to-end integration tests for the FIM pipeline."""

import random

import pytest

from fim.deps import HAS_TREE_SITTER
from generate._fim import generate_fim_examples


@pytest.fixture
def seed():
    random.seed(42)


class TestGenerateFimExamples:
    def test_produces_examples(self, simple_class_php, tmp_path, seed):
        filepath = tmp_path / "UserService.php"
        filepath.write_text(simple_class_php)
        examples = generate_fim_examples(filepath, simple_class_php, tmp_path)
        assert len(examples) > 0

    def test_every_example_has_nonempty_prefix_and_middle(self, simple_class_php, tmp_path, seed):
        filepath = tmp_path / "UserService.php"
        filepath.write_text(simple_class_php)
        examples = generate_fim_examples(filepath, simple_class_php, tmp_path)
        for ex in examples:
            assert len(ex.prefix) > 0
            assert len(ex.middle.strip()) > 0

    def test_byte_span_reconstruction(self, simple_class_php, tmp_path, seed):
        """Key invariant: for byte-offset spans, prefix + middle + suffix == original."""
        filepath = tmp_path / "UserService.php"
        filepath.write_text(simple_class_php)
        examples = generate_fim_examples(filepath, simple_class_php, tmp_path)

        byte_kinds = {"ast_single_node", "ast_aligned_span", "dev_incomplete_line",
                      "dev_bracket_content", "dev_post_comment", "char_random"}
        for ex in examples:
            if ex.span_kind in byte_kinds:
                reconstructed = ex.prefix + ex.middle + ex.suffix
                assert reconstructed == simple_class_php, (
                    f"Reconstruction failed for {ex.span_kind}: "
                    f"got {len(reconstructed)} chars, expected {len(simple_class_php)}"
                )

    def test_relative_filepath_in_examples(self, simple_class_php, tmp_path, seed):
        filepath = tmp_path / "src" / "UserService.php"
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(simple_class_php)
        examples = generate_fim_examples(filepath, simple_class_php, tmp_path)
        for ex in examples:
            assert ex.filepath == "src/UserService.php"

    def test_use_ast_false_falls_back_to_regex(self, simple_class_php, tmp_path, seed):
        filepath = tmp_path / "UserService.php"
        filepath.write_text(simple_class_php)
        examples = generate_fim_examples(
            filepath, simple_class_php, tmp_path, use_ast=False
        )
        assert len(examples) > 0
        kinds = {ex.span_kind for ex in examples}
        # Should not have AST or dev-behavior prefixed kinds
        assert not any(k.startswith("ast_") for k in kinds)
        assert not any(k.startswith("dev_") for k in kinds)

    def test_max_total_chars_respected(self, simple_class_php, tmp_path, seed):
        filepath = tmp_path / "UserService.php"
        filepath.write_text(simple_class_php)
        max_chars = 2000
        examples = generate_fim_examples(
            filepath, simple_class_php, tmp_path, max_total_chars=max_chars
        )
        for ex in examples:
            total = len(ex.prefix) + len(ex.middle) + len(ex.suffix) + len(ex.cross_file_context)
            assert total <= max_chars, (
                f"{ex.span_kind} example has {total} chars, limit is {max_chars}"
            )

    @pytest.mark.skipif(not HAS_TREE_SITTER, reason="tree-sitter not installed")
    def test_ast_mode_produces_ast_spans(self, simple_class_php, tmp_path, seed):
        filepath = tmp_path / "UserService.php"
        filepath.write_text(simple_class_php)
        examples = generate_fim_examples(
            filepath, simple_class_php, tmp_path, use_ast=True
        )
        kinds = {ex.span_kind for ex in examples}
        ast_kinds = {k for k in kinds if k.startswith("ast_")}
        assert len(ast_kinds) > 0, f"Expected AST spans, got: {kinds}"
