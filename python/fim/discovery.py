import os
import re
from pathlib import Path

SKIP_DIRS = {
    "vendor", "node_modules", ".git", ".svn", "cache", "storage",
    "public", "dist", "build", ".idea", ".vscode",
}

SKIP_PATTERNS = [
    r"\.blade\.php$",      # Laravel templates (HTML, not logic)
    r"\.min\.php$",        # Minified
    r"config/.*\.php$",    # Config files (just arrays, not useful)
    r"database/migrations",  # Migrations (boilerplate)
    r"routes/.*\.php$",    # Route definitions (declarative)
]


def find_files(root: Path, lang_config, tested_only: bool = False) -> list[Path]:
    """
    Find source files worth training on, using language-specific config
    for extensions, skip rules, and test detection.
    """
    source_files = []
    test_files = set()

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in lang_config.skip_dirs]

        rel_dir = os.path.relpath(dirpath, root)

        for fname in filenames:
            if not any(fname.endswith(ext) for ext in lang_config.extensions):
                continue

            rel_path = os.path.join(rel_dir, fname)

            if lang_config.is_test_file(rel_path, fname):
                test_files.add(rel_path)
                continue

            if any(re.search(p, rel_path) for p in lang_config.skip_patterns):
                continue

            source_files.append(Path(dirpath) / fname)

    if tested_only:
        tested_files = []
        for f in source_files:
            stem = f.stem
            has_test = any(stem in t or f"{stem}Test" in t for t in test_files)
            if has_test:
                tested_files.append(f)
        print(f"  Filtered to {len(tested_files)}/{len(source_files)} files with tests")
        return tested_files

    return source_files


def find_php_files(root: Path, tested_only: bool = False) -> list[Path]:
    """
    Find PHP source files worth training on.
    Skips vendor, config, templates, and other low-signal files.
    Backward-compatible alias for find_files() with PHP config.
    """
    from fim.language import PHP
    return find_files(root, PHP, tested_only)
