import json
import os
import pytest
from unittest.mock import patch, MagicMock

from prism_reviewer.utils.git_utils import (
    get_current_head_sha,
    get_changed_files_list,
)
from prism_reviewer.cli import _resolve_git_diff_mode_and_content


def test_get_current_head_sha():
    with patch("prism_reviewer.utils.git_utils.run_git_command", return_value="abc123def456\n"):
        sha = get_current_head_sha("/fake/repo")
        assert sha == "abc123def456"


def test_get_changed_files_list():
    mock_diff = (
        "diff --git a/src/main.py b/src/main.py\n"
        "--- a/src/main.py\n"
        "+++ b/src/main.py\n"
        "@@ -1,3 +1,4 @@\n"
        "+# new comment\n"
        "diff --git a/utils/helper.py b/utils/helper.py\n"
        "--- a/utils/helper.py\n"
        "+++ b/utils/helper.py\n"
        "@@ -1,2 +1,3 @@\n"
        "+# helper edit\n"
    )
    with patch("prism_reviewer.utils.git_utils.get_git_diff", return_value=mock_diff):
        files = get_changed_files_list("/fake/repo", "main")
        assert files == ["src/main.py", "utils/helper.py"]


def test_resolve_git_diff_mode_and_content_auto_fallback(tmp_path):
    # Setup state directory without previous sha
    state_dir = tmp_path / ".prism_reviewer"
    state_dir.mkdir()
    
    args = MagicMock()
    args.diff_mode = "auto"
    args.compare_range = None
    args.base = "main"

    logger = MagicMock()

    with patch("prism_reviewer.cli.get_current_head_sha", return_value="headsha123"), \
         patch("prism_reviewer.cli.get_git_diff", return_value="full diff content"), \
         patch("prism_reviewer.cli.get_changed_files_list", return_value=["file1.py"]):

        diff_content, is_incremental, mode, full_pr_files, current_head = _resolve_git_diff_mode_and_content(
            str(tmp_path), args, logger
        )

        assert diff_content == "full diff content"
        assert is_incremental is False
        assert mode == "auto"
        assert full_pr_files == ["file1.py"]
        assert current_head == "headsha123"


def test_resolve_git_diff_mode_and_content_incremental_success(tmp_path):
    state_dir = tmp_path / ".prism_reviewer"
    state_dir.mkdir()
    state_file = state_dir / "state.json"
    state_file.write_text(json.dumps({"last_reviewed_commit_sha": "prevsha999"}), encoding="utf-8")

    args = MagicMock()
    args.diff_mode = "auto"
    args.compare_range = None
    args.base = "main"

    logger = MagicMock()

    def mock_diff_side_effect(repo_path, base):
        if base == "prevsha999..headsha123":
            return "incremental diff content"
        return "full diff content"

    with patch("prism_reviewer.cli.get_current_head_sha", return_value="headsha123"), \
         patch("prism_reviewer.cli.get_git_diff", side_effect=mock_diff_side_effect), \
         patch("prism_reviewer.cli.get_changed_files_list", return_value=["file1.py", "file2.py"]):

        diff_content, is_incremental, mode, full_pr_files, current_head = _resolve_git_diff_mode_and_content(
            str(tmp_path), args, logger
        )

        assert diff_content == "incremental diff content"
        assert is_incremental is True
        assert mode == "auto"
        assert full_pr_files == ["file1.py", "file2.py"]
        assert current_head == "headsha123"
