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


def find_php_files(root: Path, tested_only: bool = False) -> list[Path]:
    """
    Find PHP source files worth training on.
    Skips vendor, config, templates, and other low-signal files.
    """
    php_files = []
    test_files = set()

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        rel_dir = os.path.relpath(dirpath, root)

        for fname in filenames:
            if not fname.endswith(".php"):
                continue

            rel_path = os.path.join(rel_dir, fname)

            # Track test files
            if "test" in rel_path.lower() or "Test" in fname:
                test_files.add(rel_path)
                # Don't include test files in training data by default —
                # they're useful for validation but training on tests can
                # teach the model to generate test boilerplate instead of
                # actual logic
                continue

            # Skip low-signal patterns
            if any(re.search(p, rel_path) for p in SKIP_PATTERNS):
                continue

            php_files.append(Path(dirpath) / fname)

    if tested_only:
        # Only keep files that have a corresponding test file
        # Heuristic: MyClass.php → MyClassTest.php or Tests/MyClassTest.php
        tested_files = []
        for f in php_files:
            stem = f.stem
            has_test = any(
                stem in t or f"{stem}Test" in t
                for t in test_files
            )
            if has_test:
                tested_files.append(f)
        print(f"  Filtered to {len(tested_files)}/{len(php_files)} files with tests")
        return tested_files

    return php_files
