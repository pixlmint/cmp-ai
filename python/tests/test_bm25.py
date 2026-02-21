"""Tests for BM25 index and retrieval (requires rank-bm25)."""

from fim.bm25 import _tokenize_code, build_bm25_index, retrieve_bm25_context
pytest = __import__("pytest")
pytest.importorskip("rank_bm25")


class TestTokenizeCode:
    def test_splits_on_non_alphanumeric(self):
        tokens = _tokenize_code("$this->findUser($id)")
        assert "this" in tokens
        assert "finduser" in tokens
        assert "id" in tokens

    def test_lowercases(self):
        tokens = _tokenize_code("UserService FindAll")
        assert "userservice" in tokens
        assert "findall" in tokens

    def test_drops_single_char_tokens(self):
        tokens = _tokenize_code("a bb ccc d")
        assert "a" not in tokens
        assert "d" not in tokens
        assert "bb" in tokens
        assert "ccc" in tokens


class TestBuildBm25Index:
    def test_builds_from_files(self, tmp_path):
        f1 = tmp_path / "A.php"
        f1.write_text("<?php\nclass A {\n    public function foo() {\n        return 1;\n    }\n}\n")
        f2 = tmp_path / "B.php"
        f2.write_text("<?php\nclass B {\n    public function bar() {\n        return 2;\n    }\n}\n")
        idx = build_bm25_index([f1, f2], tmp_path)
        assert idx is not None
        assert len(idx.chunks) > 0
        assert len(idx.chunk_files) == len(idx.chunks)

    def test_returns_none_for_empty_list(self, tmp_path):
        idx = build_bm25_index([], tmp_path)
        assert idx is None


class TestRetrieveBm25Context:
    def _make_index(self, tmp_path):
        f1 = tmp_path / "UserService.php"
        f1.write_text(
            "<?php\n\nclass UserService {\n\n"
            "    public function findUser(int $id): ?User {\n"
            "        return $this->repo->find($id);\n"
            "    }\n\n"
            "    public function deleteUser(int $id): void {\n"
            "        $this->repo->delete($id);\n"
            "    }\n}\n"
        )
        f2 = tmp_path / "OrderService.php"
        f2.write_text(
            "<?php\n\nclass OrderService {\n\n"
            "    public function createOrder(array $items): Order {\n"
            "        $order = new Order();\n"
            "        foreach ($items as $item) {\n"
            "            $order->addItem($item);\n"
            "        }\n"
            "        return $order;\n"
            "    }\n}\n"
        )
        return build_bm25_index([f1, f2], tmp_path)

    def test_retrieves_from_different_files(self, tmp_path):
        idx = self._make_index(tmp_path)
        assert idx is not None
        ctx = retrieve_bm25_context(
            "findUser", "", idx, "OrderService.php"
        )
        # Should find chunks from UserService, not OrderService
        if ctx:
            assert "UserService.php" in ctx

    def test_no_crash_on_unrelated_query(self, tmp_path):
        idx = self._make_index(tmp_path)
        assert idx is not None
        ctx = retrieve_bm25_context(
            "completely unrelated javascript react angular", "", idx, "Other.php"
        )
        # Should return something or empty, but not crash
        assert isinstance(ctx, str)


class TestRetrieveBm25ContextDebug:
    def _make_index(self, tmp_path):
        f1 = tmp_path / "UserService.php"
        f1.write_text(
            "<?php\n\nclass UserService {\n\n"
            "    public function findUser(int $id): ?User {\n"
            "        return $this->repo->find($id);\n"
            "    }\n\n"
            "    public function deleteUser(int $id): void {\n"
            "        $this->repo->delete($id);\n"
            "    }\n}\n"
        )
        f2 = tmp_path / "OrderService.php"
        f2.write_text(
            "<?php\n\nclass OrderService {\n\n"
            "    public function createOrder(array $items): Order {\n"
            "        $order = new Order();\n"
            "        foreach ($items as $item) {\n"
            "            $order->addItem($item);\n"
            "        }\n"
            "        return $order;\n"
            "    }\n}\n"
        )
        return build_bm25_index([f1, f2], tmp_path)

    def test_debug_returns_tuple(self, tmp_path):
        idx = self._make_index(tmp_path)
        assert idx is not None
        result = retrieve_bm25_context(
            "findUser", "", idx, "OrderService.php", debug=True
        )
        assert isinstance(result, tuple)
        ctx, debug_info = result
        assert isinstance(ctx, str)
        assert len(debug_info["query_tokens"]) > 0
        assert "finduser" in debug_info["query_tokens"]
        assert debug_info["budget"]["max_chars"] > 0

    def test_debug_false_returns_str(self, tmp_path):
        idx = self._make_index(tmp_path)
        assert idx is not None
        result = retrieve_bm25_context(
            "findUser", "", idx, "OrderService.php", debug=False
        )
        assert isinstance(result, str)

    def test_debug_scored_chunks_have_scores(self, tmp_path):
        idx = self._make_index(tmp_path)
        assert idx is not None
        ctx, debug_info = retrieve_bm25_context(
            "findUser", "", idx, "OrderService.php", debug=True
        )
        if debug_info["scored_chunks"]:
            chunk = debug_info["scored_chunks"][0]
            assert "file" in chunk
            assert "score" in chunk
            assert "selected" in chunk
            assert "length" in chunk
            assert chunk["selected"] is True

    def test_debug_empty_query(self, tmp_path):
        idx = self._make_index(tmp_path)
        assert idx is not None
        ctx, debug_info = retrieve_bm25_context(
            "", "", idx, "Other.php", debug=True
        )
        assert ctx == ""
        assert debug_info["query_tokens"] == []
        assert debug_info["scored_chunks"] == []
