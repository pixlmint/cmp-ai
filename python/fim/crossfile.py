import os
import re
from pathlib import Path


def extract_file_signature(
    source: str,
    filepath: Path,
    referenced_symbols: set[str] | None = None,
    max_lines: int = 40,
) -> str:
    """
    Extract a compact "signature" of a PHP file: namespace, use statements,
    class declaration, and method signatures (without bodies).
    This is what gets prepended as cross-file context.

    When referenced_symbols is provided, only include method/const/property
    declarations whose names are in that set (structural declarations like
    namespace, use, class are always included).
    """
    lines = source.split("\n")
    sig_lines = []

    for line in lines:
        stripped = line.strip()

        # Always include: namespace, use, class/interface/trait declarations
        if stripped.startswith(("namespace ", "use ", "class ", "interface ",
                                "trait ", "abstract class", "final class",
                                "enum ")):
            sig_lines.append(line)
            continue

        # Include method signatures (but not bodies)
        m = re.match(
            r"\s*(?:(?:public|protected|private|static|abstract|final)\s+)*"
            r"function\s+(\w+)\s*\(",
            line,
        )
        if m:
            method_name = m.group(1)
            # Filter: only include if referenced or no filter given
            if referenced_symbols is not None and method_name not in referenced_symbols:
                continue
            # Take just the signature line(s) up to the opening brace
            sig = line.rstrip()
            if "{" in sig:
                sig = sig[:sig.index("{")] + "{ ... }"
            elif ";" in sig:
                pass  # abstract method
            else:
                sig += " { ... }"
            sig_lines.append(sig)
            continue

        # Include const and property declarations
        if re.match(r"\s*(?:(?:public|protected|private|static)\s+)*"
                    r"(?:const |(?:\?\w+|\w+) \$)", stripped):
            # Filter const/property names
            if referenced_symbols is not None:
                # Extract the const/property name
                cm = re.search(r"const\s+(\w+)", stripped)
                pm = re.search(r"\$(\w+)", stripped)
                name = (cm.group(1) if cm else None) or (pm.group(1) if pm else None)
                if name and name not in referenced_symbols:
                    continue
            sig_lines.append(line)

    if not sig_lines:
        return ""

    # Apply per-file line cap
    if len(sig_lines) > max_lines:
        sig_lines = sig_lines[:max_lines]

    header = f"// --- {filepath.name} ---\n"
    return header + "\n".join(sig_lines)


def _extract_referenced_symbols(source: str) -> set[str]:
    """
    Extract identifiers referenced in a PHP source file.
    Used to filter cross-file signatures to only relevant symbols.
    """
    symbols = set()
    # Method calls: ->methodName( or ClassName::methodName(
    for m in re.finditer(r"(?:->|::)(\w+)\s*\(", source):
        symbols.add(m.group(1))
    # Static access: ClassName::CONST or ClassName::$prop
    for m in re.finditer(r"::(\w+)", source):
        symbols.add(m.group(1))
    # Class references in use/extends/implements/new/instanceof
    for m in re.finditer(r"(?:extends|implements|new|instanceof)\s+(\w+)", source):
        symbols.add(m.group(1))
    # Direct function calls
    for m in re.finditer(r"\b(\w+)\s*\(", source):
        symbols.add(m.group(1))
    return symbols


def find_related_files(
    filepath: Path,
    all_files: list[Path],
    root: Path,
    source: str,
) -> list[Path]:
    """
    Find files that are relevant context for a given file.
    Only includes files actually referenced via use/require/include — no
    same-directory heuristic (which causes context bloat).
    """
    related = []

    # 1. Parse `use` statements to find referenced classes
    use_classes = set()
    for match in re.finditer(r"use\s+([\w\\]+?)(?:\s+as\s+\w+)?;", source):
        fqcn = match.group(1)
        class_name = fqcn.split("\\")[-1]
        use_classes.add(class_name)

    # 2. Parse `require`/`include` statements to find referenced files
    require_files = set()
    for match in re.finditer(r"(?:require|include)(?:_once)?\s*\(\s*['\"]([^'\"]+?)['\"]\s*\)", source):
        file_path = match.group(1)
        filename = os.path.basename(file_path)
        filename = os.path.splitext(filename)[0]
        require_files.add(filename)

    # 3. Find files matching those class names or file names
    for f in all_files:
        if f == filepath:
            continue
        if f.stem in use_classes or f.stem in require_files:
            related.append(f)

    # Limit to top 5 most relevant
    return related[:5]


def build_cross_file_context(
    filepath: Path,
    all_files: list[Path],
    root: Path,
    source: str,
    max_tokens: int = 1024,
) -> str:
    """
    Build dependency-based cross-file context string to prepend to the FIM prefix.
    Filters signatures to only include symbols actually referenced by the target file.
    """
    related = find_related_files(filepath, all_files, root, source)
    if not related:
        return ""

    # Extract symbols referenced in the target file for filtering
    referenced = _extract_referenced_symbols(source)

    context_parts = []
    total_len = 0
    char_budget = max_tokens * 4  # rough chars-per-token estimate

    for rel_file in related:
        try:
            rel_source = rel_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Check if target extends/implements from this file — if so, include all symbols
        extends_this = any(
            rel_file.stem in line
            for line in source.split("\n")
            if re.match(r".*\b(?:extends|implements)\b", line)
        )
        filter_symbols = None if extends_this else referenced

        sig = extract_file_signature(rel_source, rel_file, referenced_symbols=filter_symbols)
        if not sig:
            continue

        if total_len + len(sig) > char_budget:
            break

        context_parts.append(sig)
        total_len += len(sig)

    if not context_parts:
        return ""

    return "\n\n".join(context_parts) + "\n\n"
