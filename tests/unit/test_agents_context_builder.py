"""Tests for the build_context_node context builder."""

import os
from unittest.mock import MagicMock, patch
import pytest

from prism_reviewer.agents.state import ReviewState
from prism_reviewer.agents.nodes import build_context_node


def _make_state(git_diff: str = "") -> ReviewState:
    return {
        "repo_path": "/tmp/test_repo",
        "git_diff": git_diff,
        "pr_title": "Test PR",
        "pr_description": "Test description",
        "repo_structure": "",
        "ast_map": {},
        "codelens_dep_summary": "",
        "codelens_search_hits": "",
        "context_content": "",
        "rules_content": "",
        "previous_signatures": [],
        "regions": [],
        "raw_findings": [],
        "verified_findings": [],
        "report_markdown": "",
    }


class TestBuildContextNode:
    @patch("prism_reviewer.agents.nodes._get_repo_structure")
    @patch("prism_reviewer.agents.nodes.UniversalASTAnalyzer")
    @patch("prism_reviewer.agents.nodes.scan_dependencies")
    @patch("prism_reviewer.agents.nodes.find_text")
    @patch("os.path.isfile")
    def test_build_context_node_success(
        self,
        mock_isfile,
        mock_find_text,
        mock_scan_deps,
        mock_ast_analyzer_class,
        mock_get_repo_structure,
    ) -> None:
        """build_context_node gathers repo files, parses AST for touched files, scans deps, and finds references."""
        # Setup mocks
        mock_get_repo_structure.return_value = "foo.py\nbar.py"
        mock_isfile.return_value = True
        
        mock_analyzer = MagicMock()
        mock_analyzer.get_ast_skeleton.return_value = {
            "symbols": [
                {"type": "function", "name": "hello", "start_line": 1, "end_line": 5}
            ]
        }
        mock_ast_analyzer_class.return_value = mock_analyzer
        
        mock_scan_deps.return_value = [
            {
                "file": "requirements.txt",
                "dependencies": ["requests==2.25.0"],
                "issues": [{"message": "requests is outdated"}]
            }
        ]
        
        mock_find_text.return_value = [
            {"file": "baz.py", "line_number": 10, "content": "import foo"}
        ]

        # Git diff touching foo.py
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "index 0000000..1234567 100644\n"
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,1 +1,2 @@\n"
            " def hello():\n"
            "+    pass\n"
        )
        
        state = _make_state(git_diff=diff)
        
        # Run node
        result = build_context_node(state)
        
        # Assertions
        assert "repo_structure" in result
        assert result["repo_structure"] == "foo.py\nbar.py"
        
        assert "ast_map" in result
        assert "foo.py" in result["ast_map"]
        assert result["ast_map"]["foo.py"]["symbols"][0]["name"] == "hello"
        
        assert "codelens_dep_summary" in result
        assert "requirements.txt" in result["codelens_dep_summary"]
        assert "requests is outdated" in result["codelens_dep_summary"]
        
        assert "codelens_search_hits" in result
        assert "References to `foo`:" in result["codelens_search_hits"]
        assert "baz.py:10: import foo" in result["codelens_search_hits"]

    @patch("prism_reviewer.agents.nodes._get_repo_structure")
    @patch("prism_reviewer.agents.nodes.UniversalASTAnalyzer")
    @patch("prism_reviewer.agents.nodes.scan_dependencies")
    @patch("prism_reviewer.agents.nodes.find_text")
    @patch("os.path.isfile")
    def test_build_context_node_skips_missing_or_binary_files(
        self,
        mock_isfile,
        mock_find_text,
        mock_scan_deps,
        mock_ast_analyzer_class,
        mock_get_repo_structure,
    ) -> None:
        """build_context_node gracefully skips AST parsing for non-existent or failing files."""
        mock_get_repo_structure.return_value = "missing.py\nbad.py"
        
        # missing.py isfile=False, bad.py isfile=True but throws an exception in AST parser
        def isfile_side_effect(path):
            if "missing.py" in path:
                return False
            return True
        mock_isfile.side_effect = isfile_side_effect
        
        mock_analyzer = MagicMock()
        mock_analyzer.get_ast_skeleton.side_effect = Exception("Failed to parse AST")
        mock_ast_analyzer_class.return_value = mock_analyzer
        
        mock_scan_deps.return_value = []
        mock_find_text.return_value = []
        
        diff = (
            "diff --git a/missing.py b/missing.py\n"
            "+++ b/missing.py\n"
            "diff --git a/bad.py b/bad.py\n"
            "+++ b/bad.py\n"
        )
        
        state = _make_state(git_diff=diff)
        
        result = build_context_node(state)
        
        assert "ast_map" in result
        assert result["ast_map"] == {}  # both skipped
