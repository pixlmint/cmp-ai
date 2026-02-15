"""Tests for cross-file context: signatures, related files, and context building."""

from pathlib import Path

from fim.crossfile import (
    extract_file_signature,
    _extract_referenced_symbols,
    find_related_files,
    build_cross_file_context,
)


class TestExtractFileSignature:
    def test_includes_namespace_and_class(self, dependency_provider_php):
        sig = extract_file_signature(dependency_provider_php, Path("UserService.php"))
        assert "namespace App\\Services" in sig
        assert "class UserService" in sig

    def test_includes_method_signatures(self, dependency_provider_php):
        sig = extract_file_signature(dependency_provider_php, Path("UserService.php"))
        assert "findUser" in sig
        assert "deleteUser" in sig
        assert "listUsers" in sig

    def test_method_bodies_replaced_with_ellipsis(self, dependency_provider_php):
        sig = extract_file_signature(dependency_provider_php, Path("UserService.php"))
        assert "{ ... }" in sig

    def test_referenced_symbols_filter_limits_methods(self, dependency_provider_php):
        sig = extract_file_signature(
            dependency_provider_php,
            Path("UserService.php"),
            referenced_symbols={"findUser"},
        )
        assert "findUser" in sig
        assert "deleteUser" not in sig
        assert "listUsers" not in sig

    def test_header_contains_filename(self, dependency_provider_php):
        sig = extract_file_signature(dependency_provider_php, Path("UserService.php"))
        assert "// --- UserService.php ---" in sig


class TestExtractReferencedSymbols:
    def test_finds_method_calls(self):
        source = "$this->findActive();\n$user->save();"
        symbols = _extract_referenced_symbols(source)
        assert "findActive" in symbols
        assert "save" in symbols

    def test_finds_static_calls(self):
        source = "User::findOrFail($id);"
        symbols = _extract_referenced_symbols(source)
        assert "findOrFail" in symbols

    def test_finds_class_references(self):
        source = "class Foo extends Bar implements Baz {}"
        symbols = _extract_referenced_symbols(source)
        assert "Bar" in symbols
        assert "Baz" in symbols

    def test_finds_new_instances(self):
        source = "$obj = new UserService();"
        symbols = _extract_referenced_symbols(source)
        assert "UserService" in symbols


class TestFindRelatedFiles:
    def test_matches_use_class_to_file_stems(self, tmp_path, dependency_target_php):
        # Create provider files
        svc = tmp_path / "UserService.php"
        svc.write_text("<?php class UserService {}")
        model = tmp_path / "User.php"
        model.write_text("<?php class User {}")
        other = tmp_path / "OrderService.php"
        other.write_text("<?php class OrderService {}")

        target = tmp_path / "UserController.php"
        target.write_text(dependency_target_php)

        all_files = [svc, model, other, target]
        related = find_related_files(target, all_files, tmp_path, dependency_target_php)

        stems = {f.stem for f in related}
        assert "UserService" in stems
        assert "User" in stems
        assert "UserController" not in stems  # excludes self

    def test_excludes_self(self, tmp_path):
        f = tmp_path / "Foo.php"
        f.write_text("<?php\nuse App\\Foo;")
        related = find_related_files(f, [f], tmp_path, f.read_text())
        assert len(related) == 0

    def test_caps_at_five(self, tmp_path):
        source = "<?php\n" + "\n".join(f"use App\\Dep{i};" for i in range(10))
        target = tmp_path / "Target.php"
        target.write_text(source)
        all_files = [target]
        for i in range(10):
            f = tmp_path / f"Dep{i}.php"
            f.write_text(f"<?php class Dep{i} {{}}")
            all_files.append(f)

        related = find_related_files(target, all_files, tmp_path, source)
        assert len(related) <= 5


class TestBuildCrossFileContext:
    def test_combines_filtered_signatures(self, tmp_path, dependency_target_php, dependency_provider_php):
        target = tmp_path / "UserController.php"
        target.write_text(dependency_target_php)
        provider = tmp_path / "UserService.php"
        provider.write_text(dependency_provider_php)
        all_files = [target, provider]

        ctx = build_cross_file_context(target, all_files, tmp_path, dependency_target_php)
        assert "UserService.php" in ctx
        assert len(ctx) > 0

    def test_empty_when_no_deps(self, tmp_path):
        source = "<?php\nclass Isolated {}\n"
        target = tmp_path / "Isolated.php"
        target.write_text(source)
        ctx = build_cross_file_context(target, [target], tmp_path, source)
        assert ctx == ""
