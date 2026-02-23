import random

from fim.types import CodeSpan


def generate_char_level_splits(
    source: str,
    num_splits: int = 0,
    min_middle_chars: int = 10,
    max_middle_chars: int = 500,
) -> list[CodeSpan]:
    """
    Generate random character-level split points for FIM training.

    Per Bavarian et al. 2022, character-level random splitting is critical
    for teaching the model to handle partial-line completions. Line-level
    splitting alone "failed catastrophically when asked to complete partial
    lines."

    Returns CodeSpan objects where start_line/end_line encode character
    offsets (not line numbers) — indicated by kind="char_random".
    """
    if len(source) < min_middle_chars * 3:
        return []

    # Default: ~1 split per 80 lines (targets ~10% of total spans)
    if num_splits <= 0:
        num_splits = max(1, source.count("\n") // 100)

    spans = []
    for _ in range(num_splits):
        # Pick a random middle length
        mid_len = random.randint(min_middle_chars, min(max_middle_chars, len(source) // 3))
        # Pick a random start point leaving room for prefix and suffix
        max_start = len(source) - mid_len - 1
        if max_start < 1:
            continue
        start = random.randint(1, max_start)

        # We store char offsets in start_line/end_line for char_random spans
        spans.append(CodeSpan(
            kind="char_random",
            start_line=start,           # char offset (not line number)
            end_line=start + mid_len,   # char offset (not line number)
            name="",
            indent=0,
        ))

    return spans
