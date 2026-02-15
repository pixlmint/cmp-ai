# Tree-sitter for AST-aware span extraction (Phase 1)
try:
    import tree_sitter_php as tsphp
    from tree_sitter import Language, Parser, Node
    PHP_LANGUAGE = Language(tsphp.language_php())  # language_php() = PHP with HTML
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False
    Parser = None
    Node = None
    PHP_LANGUAGE = None

# BM25 for cross-file retrieval (Phase 3)
try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False
    BM25Okapi = None
