"""Tests for quality filters, entropy, and complexity scoring."""

from generate._quality import (
    _char_entropy,
    filter_low_quality_examples,
    compute_complexity_score,
)
from tests.conftest import make_example


class TestCharEntropy:
    def test_zero_entropy_for_uniform_string(self):
        assert _char_entropy("aaaaaaa") == 0.0

    def test_high_entropy_for_code(self):
        code = "public function findUser(int $id): ?User { return $this->repo->find($id); }"
        assert _char_entropy(code) > 4.0

    def test_zero_for_empty(self):
        assert _char_entropy("") == 0.0

    def test_single_char(self):
        assert _char_entropy("x") == 0.0

    def test_two_different_chars(self):
        # "ab" -> each has probability 0.5, entropy = 1.0 bit
        assert abs(_char_entropy("ab") - 1.0) < 0.01


class TestFilterLowQualityExamples:
    def test_keeps_good_example(self):
        ex = make_example(
            prefix="<?php\nclass Foo {\n",
            middle="    public function bar() { return 1; }\n    public function baz() { return 2; }\n",
            suffix="}\n",
        )
        kept, rejected, _rejected_by_kind = filter_low_quality_examples([ex])
        assert len(kept) == 1
        assert len(rejected) == 0

    def test_rejects_repetitive_middle(self):
        # >50% duplicate lines
        repeated = "\n".join(["$x = 1;"] * 10 + ["$y = 2;"] * 2)
        ex = make_example(middle=repeated)
        kept, rejected, _rejected_by_kind = filter_low_quality_examples([ex])
        assert len(rejected) == 1
        assert len(kept) == 0

    def test_rejects_low_entropy(self):
        ex = make_example(middle="aaa aaa aaa")
        kept, rejected, _rejected_by_kind = filter_low_quality_examples([ex])
        assert len(rejected) == 1

    def test_rejects_comment_only(self):
        comments = "\n".join([
            "// this is a comment",
            "// another comment",
            "// yet another",
            "// and more",
            "// final one",
        ])
        ex = make_example(middle=comments)
        kept, rejected, _rejected_by_kind = filter_low_quality_examples([ex])
        assert len(rejected) == 1

    def test_rejects_tiny_ratio(self):
        # middle < 3% of total
        big = "x" * 1000
        ex = make_example(prefix=big, middle="ab cd ef", suffix=big)
        kept, rejected, _rejected_by_kind = filter_low_quality_examples([ex])
        assert len(rejected) == 1

    def test_rejects_huge_ratio(self):
        # middle > 80% of total
        big_middle = "$x = 1;\n" * 100
        ex = make_example(prefix="<?php\n", middle=big_middle, suffix="")
        kept, rejected, _rejected_by_kind = filter_low_quality_examples([ex])
        assert len(rejected) == 1

    def test_skip_quality_filters_bypasses_check(self):
        """skip_quality_filters on FIMExample should bypass named checks."""
        comments = "\n".join([
            "// this is a comment",
            "// another comment",
            "// yet another",
            "// and more",
            "// final one",
        ])
        ex = make_example(middle=comments)
        # Without exclusion: rejected
        kept, rejected, _ = filter_low_quality_examples([ex])
        assert len(rejected) == 1
        # With comment_only exclusion: kept
        ex.skip_quality_filters = frozenset({"comment_only"})
        kept, rejected, _ = filter_low_quality_examples([ex])
        assert len(rejected) == 0
        assert len(kept) == 1

    def test_mixed_batch_counts(self):
        good = make_example(
            prefix="<?php\nnamespace App;\n\nclass A {\n    private int $x;\n    private int $y;\n\n",
            middle="    public function x(): int { return $this->x; }\n    public function y(): int { return $this->y; }\n",
            suffix="\n    public function z(): void { echo 'done'; }\n}\n",
        )
        bad_entropy = make_example(middle="aaa aaa aaa")
        kept, rejected, _rejected_by_kind = filter_low_quality_examples([good, bad_entropy])
        assert len(kept) == 1
        assert len(rejected) == 1


class TestComputeComplexityScore:
    def test_complex_higher_than_simple(self):
        """Complexity = identifier density (idents per byte). Code with more
        identifiers relative to structural tokens scores higher."""
        complex_code = """\
<?php
class UserService {
    private UserRepository $repo;
    public function findActive(): array {
        $users = $this->repo->findAll();
        return array_filter($users, fn(User $u) => $u->isActive());
    }
    public function deactivate(User $user): void {
        $user->setActive(false);
        $this->repo->save($user);
    }
}
"""
        # Low-identifier code: mostly strings and comments
        low_ident_code = """\
<?php
/*
 * This is a configuration file with lots of comments
 * and string literals but very few actual identifiers.
 * It serves as documentation for the system.
 */
echo "Hello world, this is a very long string with no identifiers";
echo "Another long string literal that takes up many bytes here";
"""
        assert compute_complexity_score(complex_code) > compute_complexity_score(low_ident_code)

    def test_empty_returns_zero(self):
        assert compute_complexity_score("") == 0.0
