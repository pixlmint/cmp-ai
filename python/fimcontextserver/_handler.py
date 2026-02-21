"""Request handling with project state caching."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from fim.bm25 import build_bm25_index, retrieve_bm25_context
from fim.crossfile import build_cross_file_context
from fim.deps import HAS_BM25
from fim.discovery import find_files
from fim.language import LanguageConfig, get_language
from fim.types import BM25Index

log = logging.getLogger(__name__)


@dataclass
class ProjectState:
    root: Path
    source_files: list[Path]
    lang_config: LanguageConfig
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
        lang_config = get_language(params.get("language", "php"))

        source_files = find_files(project_root, lang_config)
        for inc_dir in include_paths:
            source_files.extend(find_files(inc_dir, lang_config))

        bm25_index = None
        bm25_chunks = 0
        if use_bm25 and HAS_BM25:
            bm25_index = build_bm25_index(source_files, project_root)
            if bm25_index:
                bm25_chunks = len(bm25_index.chunks)

        self._state = ProjectState(
            root=project_root,
            source_files=source_files,
            lang_config=lang_config,
            bm25_index=bm25_index,
        )

        log.info("initialized: %d files, %d BM25 chunks", len(source_files), bm25_chunks)
        return {"file_count": len(source_files), "bm25_chunks": bm25_chunks}

    def handle_get_context(self, params: dict) -> dict:
        if self._state is None:
            raise RuntimeError("not initialized")

        filepath = Path(params["filepath"])
        content = params["content"]
        cursor_offset = params.get("cursor_offset", len(content) // 2)
        debug = params.get("debug", False)

        # Dependency-based cross-file context
        cross_result = build_cross_file_context(
            filepath,
            self._state.source_files,
            self._state.root,
            content,
            lang_config=self._state.lang_config,
            debug=debug,
        )

        if debug:
            cross_ctx, cross_debug = cross_result
            context = _format_cross_debug(cross_debug) + cross_ctx
        else:
            context = cross_result

        # BM25 context using code around cursor as query
        if self._state.bm25_index is not None:
            window = 500
            start = max(0, cursor_offset - window)
            end = min(len(content), cursor_offset + window)
            query_text = content[start:end]

            rel_path = str(filepath.relative_to(self._state.root)) if self._state.root in filepath.parents else str(filepath)
            bm25_result = retrieve_bm25_context(
                query_text, "", self._state.bm25_index, rel_path,
                debug=debug,
            )

            if debug:
                bm25_ctx, bm25_debug = bm25_result
                context += _format_bm25_debug(bm25_debug) + bm25_ctx
            else:
                context += bm25_result

        return {"context": context}

    def handle_shutdown(self, params: dict) -> None:
        self._state = None
        self.should_exit = True
        return None


def _format_cross_debug(debug_info: dict) -> str:
    lines = ["// [DEBUG] Cross-file context"]

    related = debug_info.get("related_files", [])
    lines.append(f"// [DEBUG]   Related files ({len(related)}): {', '.join(related)}")

    symbols = debug_info.get("referenced_symbols", set())
    symbol_list = sorted(symbols) if symbols else []
    lines.append(f"// [DEBUG]   Referenced symbols ({len(symbol_list)}): {', '.join(symbol_list)}")

    for sig in debug_info.get("signatures", []):
        status = "included" if sig["included"] else "excluded - budget"
        lines.append(f"// [DEBUG]   Signature: {sig['file']} ({sig['sig_length']} chars, {status})")

    budget = debug_info.get("budget", {})
    lines.append(f"// [DEBUG]   Budget: {budget.get('used_chars', 0)}/{budget.get('max_chars', 0)} chars used")

    return "\n".join(lines) + "\n"


def _format_bm25_debug(debug_info: dict) -> str:
    lines = ["// [DEBUG] BM25 context"]

    tokens = debug_info.get("query_tokens", [])
    token_display = ", ".join(tokens[:20])
    lines.append(f"// [DEBUG]   Query tokens ({len(tokens)}): {token_display}")

    for chunk in debug_info.get("scored_chunks", []):
        status = "selected" if chunk["selected"] else "skipped - budget"
        lines.append(f"// [DEBUG]   Chunk: {chunk['file']} (score={chunk['score']}, {status}, {chunk['length']} chars)")

    budget = debug_info.get("budget", {})
    lines.append(f"// [DEBUG]   Budget: {budget.get('used_chars', 0)}/{budget.get('max_chars', 0)} chars used")

    return "\n".join(lines) + "\n"
