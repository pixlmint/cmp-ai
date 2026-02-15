"""Request handling with project state caching."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from fim.bm25 import build_bm25_index, retrieve_bm25_context
from fim.crossfile import build_cross_file_context
from fim.deps import HAS_BM25
from fim.discovery import find_php_files
from fim.types import BM25Index

log = logging.getLogger(__name__)


@dataclass
class ProjectState:
    root: Path
    php_files: list[Path]
    bm25_index: BM25Index | None = None
    sig_cache: dict[Path, tuple[float, str]] = field(default_factory=dict)


class Handler:
    def __init__(self):
        self._state: ProjectState | None = None
        self.should_exit: bool = False

    def handle_initialize(self, params: dict) -> dict:
        project_root = Path(params["project_root"])
        include_paths = [Path(p) for p in params.get("include_paths", [])]
        use_bm25 = params.get("bm25", False)

        php_files = find_php_files(project_root)
        for inc_dir in include_paths:
            php_files.extend(find_php_files(inc_dir))

        bm25_index = None
        bm25_chunks = 0
        if use_bm25 and HAS_BM25:
            bm25_index = build_bm25_index(php_files, project_root)
            if bm25_index:
                bm25_chunks = len(bm25_index.chunks)

        self._state = ProjectState(
            root=project_root,
            php_files=php_files,
            bm25_index=bm25_index,
        )

        log.info("initialized: %d files, %d BM25 chunks", len(php_files), bm25_chunks)
        return {"file_count": len(php_files), "bm25_chunks": bm25_chunks}

    def handle_get_context(self, params: dict) -> dict:
        if self._state is None:
            raise RuntimeError("not initialized")

        filepath = Path(params["filepath"])
        content = params["content"]
        cursor_offset = params.get("cursor_offset", len(content) // 2)

        # Dependency-based cross-file context
        context = build_cross_file_context(
            filepath,
            self._state.php_files,
            self._state.root,
            content,
        )

        # BM25 context using code around cursor as query
        if self._state.bm25_index is not None:
            window = 500
            start = max(0, cursor_offset - window)
            end = min(len(content), cursor_offset + window)
            query_text = content[start:end]

            rel_path = str(filepath.relative_to(self._state.root)) if self._state.root in filepath.parents else str(filepath)
            bm25_ctx = retrieve_bm25_context(
                query_text, "", self._state.bm25_index, rel_path,
            )
            context += bm25_ctx

        return {"context": context}

    def handle_shutdown(self, params: dict) -> None:
        self._state = None
        self.should_exit = True
        return None
