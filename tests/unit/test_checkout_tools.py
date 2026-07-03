import os
import pytest
import json
from unittest.mock import patch, MagicMock
from prism_reviewer.utils.git_utils import run_git_command, get_git_diff, get_repo_structure, get_file_content_at_commit
from prism_reviewer.codelens.dependency_scanner import scan_dependencies, parse_requirements_txt, parse_package_json, parse_pyproject_toml
from prism_reviewer.codelens.searcher import find_text, get_full_file, get_related_files, get_file_methods

# ----------------- Git Utils Tests -----------------

@patch("subprocess.run")
def test_run_git_command_success(mock_run, tmp_path):
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="mock diff output\n",
        stderr=""
    )
    result = run_git_command(str(tmp_path), ["diff"])
    assert result == "mock diff output\n"
    mock_run.assert_called_once()


@patch("subprocess.run")
def test_get_git_diff(mock_run, tmp_path):
    mock_run.return_value = MagicMock(stdout="diff content", stderr="")
    res = get_git_diff(str(tmp_path), "staged")
    assert res == "diff content"
    mock_run.assert_called_with(
        ["git", "diff", "--cached"],
        cwd=str(tmp_path),
        stdout=-1,
        stderr=-1,
        text=True,
        check=True,
        encoding="utf-8",
        errors="ignore"
    )


@patch("subprocess.run")
def test_get_repo_structure(mock_run, tmp_path):
    mock_run.return_value = MagicMock(stdout="src/main.py\nsrc/utils.py\nREADME.md\n", stderr="")
    structure = get_repo_structure(str(tmp_path))
    
    assert structure["type"] == "directory"
    # Find child directories or files
    children = structure["children"]
    # We should have README.md and src
    assert "README.md" in [c["name"] for c in children]
    src_node = next(c for c in children if c["name"] == "src")
    assert src_node["type"] == "directory"
    assert "main.py" in [c["name"] for c in src_node["children"]]


@patch("subprocess.run")
def test_get_file_content_at_commit(mock_run, tmp_path):
    mock_run.return_value = MagicMock(stdout="some content at commit", stderr="")
    res = get_file_content_at_commit(str(tmp_path), "src/main.py", "v1.0")
    assert res == "some content at commit"


# ----------------- Dependency Scanner Tests -----------------

def test_parse_requirements_txt(tmp_path):
    content = """
# comment
requests==2.26.0
flask>=2.0.0
    """
    req_file = tmp_path / "requirements.txt"
    req_file.write_text(content, encoding="utf-8")
    
    res = parse_requirements_txt(str(req_file))
    deps = res["dependencies"]
    issues = res["issues"]
    
    assert len(deps) == 2
    assert deps[0]["name"] == "requests"
    assert deps[0]["specifier"] == "==2.26.0"
    
    assert deps[1]["name"] == "flask"
    assert deps[1]["specifier"] == ">=2.0.0"
    
    # flask is not pinned with ==, should have warning
    assert len(issues) == 1
    assert "flask" in issues[0]["message"]


def test_parse_package_json(tmp_path):
    content = {
        "dependencies": {
            "lodash": "^4.17.21"
        },
        "devDependencies": {
            "typescript": "*"
        }
    }
    pkg_file = tmp_path / "package.json"
    pkg_file.write_text(json.dumps(content), encoding="utf-8")
    
    res = parse_package_json(str(pkg_file))
    deps = res["dependencies"]
    issues = res["issues"]
    
    assert len(deps) == 2
    assert any(d["name"] == "lodash" and d["specifier"] == "^4.17.21" for d in deps)
    assert any(d["name"] == "typescript" and d["specifier"] == "*" for d in deps)
    
    # typescript has '*', should have issue
    assert len(issues) == 1
    assert "typescript" in issues[0]["message"]


# ----------------- Searcher Tests -----------------

def test_find_text(tmp_path):
    # Setup files in tmp_path
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "foo.py").write_text("def my_awesome_func():\n    pass\n", encoding="utf-8")
    (tmp_path / "src" / "bar.py").write_text("import foo\nfoo.my_awesome_func()\n", encoding="utf-8")
    (tmp_path / "ignore_me.txt").write_text("my_awesome_func is here\n", encoding="utf-8")
    
    # Match query
    results = find_text(str(tmp_path), "my_awesome_func", extension_filter=[".py"])
    assert len(results) == 2
    assert any(r["file"] == "src/foo.py" and r["line_number"] == 1 for r in results)
    assert any(r["file"] == "src/bar.py" and r["line_number"] == 2 for r in results)


def test_get_full_file(tmp_path):
    file_path = tmp_path / "foo.py"
    file_path.write_text("print('hello')", encoding="utf-8")
    content = get_full_file(str(tmp_path), "foo.py")
    assert content == "print('hello')"


def test_get_related_files(tmp_path):
    (tmp_path / "src").mkdir()
    foo_file = tmp_path / "src" / "foo.py"
    foo_file.write_text("print('foo')", encoding="utf-8")
    
    bar_file = tmp_path / "src" / "bar.py"
    bar_file.write_text("import foo", encoding="utf-8")
    
    test_foo_file = tmp_path / "src" / "test_foo.py"
    test_foo_file.write_text("import unittest", encoding="utf-8")

    related = get_related_files(str(tmp_path), "src/foo.py")
    # should find proximity (bar.py, test_foo.py), name matching (test_foo.py), import search (bar.py)
    assert "src/bar.py" in related
    assert "src/test_foo.py" in related


# ----------------- Robustness Fallback Tests -----------------

@patch("prism_reviewer.utils.git_utils.run_git_command")
def test_git_utils_fallbacks_on_failure(mock_run):
    mock_run.side_effect = Exception("git error")
    
    # 1. get_git_diff
    assert get_git_diff("dummy_path") == ""
    
    # 2. get_repo_structure
    struct = get_repo_structure("dummy_path")
    assert struct["type"] == "directory"
    assert struct["children"] == []
    
    # 3. get_file_content_at_commit
    assert get_file_content_at_commit("dummy_path", "some_file.py") == ""


def test_dependency_scanner_fallback_on_failure():
    # If os.path.join or other methods raise inside scan_dependencies
    with patch("os.path.join", side_effect=Exception("fs error")):
        assert scan_dependencies("dummy_path") == []


def test_searcher_fallbacks_on_failure():
    # 1. find_text regex compilation error fallback
    assert find_text("dummy_path", "[invalid regex") == []
    
    # 2. find_text walkthrough error fallback
    with patch("os.walk", side_effect=Exception("walk error")):
        assert find_text("dummy_path", "query") == []
        
    # 3. get_full_file non-existent or access error fallback
    assert get_full_file("dummy_path", "non_existent.py") == ""
    
    # 4. get_related_files walk error fallback
    with patch("os.walk", side_effect=Exception("walk error")):
        assert get_related_files("dummy_path", "some_file.py") == []

    # 5. get_file_methods AST analyzer error fallback
    assert get_file_methods("dummy_path", "non_existent.py")["mode"] == "error"

