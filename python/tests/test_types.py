"""Tests for FIMConfig, FIMExample, and CodeSpan — documents the exact JSONL
format consumed by training frameworks."""

from fim.types import FIM_CONFIGS, CodeSpan
from tests.conftest import make_example


class TestFIMConfig:
    def test_format_psm_qwen(self, qwen_config):
        result = qwen_config.format_psm("PRE", "MID", "SUF")
        assert result == (
            "<|fim_prefix|>PRE"
            "<|fim_suffix|>SUF"
            "<|fim_middle|>MID"
            "<|endoftext|>"
        )

    def test_format_psm_codellama(self, codellama_config):
        result = codellama_config.format_psm("PRE", "MID", "SUF")
        assert result == "<PRE>PRE<SUF>SUF<MID>MID</s>"

    def test_psm_order_prefix_before_suffix_before_middle(self, qwen_config):
        """PSM = prefix-suffix-middle ordering in the output string."""
        result = qwen_config.format_psm("AAA", "CCC", "BBB")
        assert result.index("AAA") < result.index("BBB") < result.index("CCC")

    def test_all_configs_have_required_tokens(self):
        for name, cfg in FIM_CONFIGS.items():
            assert cfg.prefix_tok, f"{name} missing prefix_tok"
            assert cfg.suffix_tok, f"{name} missing suffix_tok"
            assert cfg.middle_tok, f"{name} missing middle_tok"
            assert cfg.eot_tok, f"{name} missing eot_tok"


class TestFIMExample:
    def test_to_training_format_structure(self, qwen_config):
        ex = make_example()
        result = ex.to_training_format(qwen_config)

        assert "text" in result
        assert "prefix" in result
        assert "middle" in result
        assert "suffix" in result
        assert "filepath" in result
        assert "span_kind" in result
        assert "span_name" in result
        assert "middle_lines" in result
        assert "complexity_score" in result

    def test_to_training_format_text_is_psm(self, qwen_config):
        ex = make_example(prefix="P", middle="M", suffix="S")
        result = ex.to_training_format(qwen_config)
        expected = qwen_config.format_psm("P", "M", "S")
        assert result["text"] == expected

    def test_cross_file_context_prepended_to_prefix(self, qwen_config):
        ctx = "// --- Dep.php ---\nclass Dep { ... }\n\n"
        ex = make_example(prefix="<?php\n", cross_file_context=ctx)
        result = ex.to_training_format(qwen_config)
        assert result["prefix"] == ctx + "<?php\n"
        assert result["text"].startswith("<|fim_prefix|>" + ctx)

    def test_middle_between_middle_tok_and_eot(self, qwen_config):
        ex = make_example(middle="return 42;")
        result = ex.to_training_format(qwen_config)
        text = result["text"]
        mid_start = text.index("<|fim_middle|>") + len("<|fim_middle|>")
        mid_end = text.index("<|endoftext|>")
        assert text[mid_start:mid_end] == "return 42;"

    def test_metadata_fields(self):
        ex = make_example(filepath="src/Foo.php", span_kind="block", span_name="loop")
        result = ex.to_training_format(FIM_CONFIGS["qwen2.5-coder"])
        assert result["filepath"] == "src/Foo.php"
        assert result["span_kind"] == "block"
        assert result["span_name"] == "loop"


class TestCodeSpan:
    def test_byte_offset_span(self):
        span = CodeSpan(
            kind="ast_single_node",
            start_line=5,
            end_line=10,
            name="myFunc",
            start_byte=100,
            end_byte=250,
        )
        assert span.start_byte == 100
        assert span.end_byte == 250
        assert span.kind == "ast_single_node"

    def test_line_offset_span(self):
        span = CodeSpan(kind="function_body", start_line=5, end_line=10, name="foo")
        assert span.start_byte == -1
        assert span.end_byte == -1

    def test_char_offset_span(self):
        """char_random spans store char offsets in start_line/end_line."""
        span = CodeSpan(kind="char_random", start_line=42, end_line=142)
        assert span.start_line == 42
        assert span.end_line == 142
        assert span.start_byte == -1
