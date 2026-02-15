"""Tests for file discovery and filtering rules."""

from fim.discovery import find_php_files


def _write(path, content="<?php\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class TestFindPhpFiles:
    def test_finds_php_files(self, tmp_path):
        _write(tmp_path / "src" / "Foo.php")
        _write(tmp_path / "src" / "Bar.php")
        _write(tmp_path / "src" / "utils.js", "// js")  # not PHP
        result = find_php_files(tmp_path)
        names = {f.name for f in result}
        assert names == {"Foo.php", "Bar.php"}

    def test_skips_vendor(self, tmp_path):
        _write(tmp_path / "src" / "App.php")
        _write(tmp_path / "vendor" / "lib" / "Dep.php")
        result = find_php_files(tmp_path)
        names = {f.name for f in result}
        assert "App.php" in names
        assert "Dep.php" not in names

    def test_skips_blade_templates(self, tmp_path):
        _write(tmp_path / "resources" / "views" / "home.blade.php")
        _write(tmp_path / "src" / "Real.php")
        result = find_php_files(tmp_path)
        names = {f.name for f in result}
        assert "home.blade.php" not in names
        assert "Real.php" in names

    def test_skips_test_files(self, tmp_path):
        _write(tmp_path / "src" / "User.php")
        _write(tmp_path / "tests" / "UserTest.php")
        result = find_php_files(tmp_path)
        names = {f.name for f in result}
        assert "User.php" in names
        assert "UserTest.php" not in names

    def test_tested_only_keeps_files_with_tests(self, tmp_path):
        _write(tmp_path / "src" / "User.php")
        _write(tmp_path / "src" / "Order.php")
        _write(tmp_path / "tests" / "UserTest.php")
        result = find_php_files(tmp_path, tested_only=True)
        names = {f.name for f in result}
        assert "User.php" in names
        assert "Order.php" not in names

    def test_skips_config_directory(self, tmp_path):
        _write(tmp_path / "config" / "app.php")
        _write(tmp_path / "src" / "App.php")
        result = find_php_files(tmp_path)
        # config/app.php matched by SKIP_PATTERNS r"config/.*\.php$"
        result_rel = {str(f.relative_to(tmp_path)) for f in result}
        assert "src/App.php" in result_rel
        assert not any(p.startswith("config/") for p in result_rel)

    def test_skips_routes_directory(self, tmp_path):
        _write(tmp_path / "routes" / "web.php")
        _write(tmp_path / "src" / "Router.php")
        result = find_php_files(tmp_path)
        result_rel = {str(f.relative_to(tmp_path)) for f in result}
        assert "src/Router.php" in result_rel
        assert not any(p.startswith("routes/") for p in result_rel)
