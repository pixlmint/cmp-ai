from dataclasses import dataclass, asdict


@dataclass
class FIMConfig:
    """FIM special tokens per base model family."""
    prefix_tok: str
    suffix_tok: str
    middle_tok: str
    eot_tok: str = "<|endoftext|>"

    # PSM = prefix-suffix-middle (the standard FIM training order)
    def format_psm(self, prefix: str, middle: str, suffix: str) -> str:
        """Format a training example in PSM order (most common for training)."""
        return (
            f"{self.prefix_tok}{prefix}"
            f"{self.suffix_tok}{suffix}"
            f"{self.middle_tok}{middle}"
            f"{self.eot_tok}"
        )


FIM_CONFIGS = {
    "qwen2.5-coder": FIMConfig(
        prefix_tok="<|fim_prefix|>",
        suffix_tok="<|fim_suffix|>",
        middle_tok="<|fim_middle|>",
        eot_tok="<|endoftext|>",
    ),
    "granite-code": FIMConfig(
        prefix_tok="<fim_prefix>",
        suffix_tok="<fim_suffix>",
        middle_tok="<fim_middle>",
        eot_tok="<|endoftext|>",
    ),
    "codellama": FIMConfig(
        prefix_tok="<PRE>",
        suffix_tok="<SUF>",
        middle_tok="<MID>",
        eot_tok="</s>",
    ),
    "starcoder": FIMConfig(
        prefix_tok="<fim_prefix>",
        suffix_tok="<fim_suffix>",
        middle_tok="<fim_middle>",
        eot_tok="<|endoftext|>",
    ),
}


@dataclass
class CodeSpan:
    """A span of code that can be used as a FIM middle section."""
    kind: str          # "function", "method", "block", "expression", "line"
    start_line: int    # 0-indexed
    end_line: int      # 0-indexed, inclusive
    name: str = ""     # function/method name if applicable
    indent: int = 0    # indentation level
    start_byte: int = -1  # byte offset (when set, used instead of line numbers)
    end_byte: int = -1    # byte offset (when set, used instead of line numbers)


@dataclass
class FIMExample:
    """A single FIM training example."""
    filepath: str
    span_kind: str
    span_name: str
    prefix: str
    middle: str
    suffix: str
    cross_file_context: str = ""

    # Metadata for analysis
    complexity_score: float = 0.0
    middle_lines: int = 0
    total_lines: int = 0

    def to_training_format(self, fim_config: FIMConfig) -> dict:
        """Convert to the JSONL format expected by training frameworks."""
        full_prefix = self.cross_file_context + self.prefix
        formatted = fim_config.format_psm(full_prefix, self.middle, self.suffix)
        return {
            "text": formatted,
            # Also include structured version for frameworks that want it
            "prefix": full_prefix,
            "middle": self.middle,
            "suffix": self.suffix,
            # Metadata
            "filepath": self.filepath,
            "span_kind": self.span_kind,
            "span_name": self.span_name,
            "middle_lines": self.middle_lines,
            "complexity_score": self.complexity_score,
        }


@dataclass
class BM25Index:
    """Pre-built BM25 index over code chunks from the entire repo."""
    bm25: object  # BM25Okapi instance
    chunks: list[str]           # the actual text chunks
    chunk_files: list[str]      # source filepath for each chunk


MIN_MIDDLE_WORDS = 3  # Minimum whitespace-delimited words in middle section
