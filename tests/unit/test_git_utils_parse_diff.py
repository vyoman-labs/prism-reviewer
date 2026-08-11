"""Tests for parse_diff_changed_lines() in utils/git_utils.py."""

import pytest

from prism_reviewer.utils.git_utils import normalize_file_path, parse_diff_changed_lines


class TestNormalizeFilePath:
    def test_normalize_empty(self) -> None:
        assert normalize_file_path("") == ""

    def test_normalize_prefixes(self) -> None:
        assert normalize_file_path("./src/main.py") == "src/main.py"
        assert normalize_file_path("a/src/main.py") == "src/main.py"
        assert normalize_file_path("b/src/main.py") == "src/main.py"
        assert normalize_file_path("/src/main.py") == "src/main.py"

    def test_normalize_windows_slashes(self) -> None:
        assert normalize_file_path("src\\main.py") == "src/main.py"
        assert normalize_file_path(".\\a\\src\\main.py") == "src/main.py"


SINGLE_FILE_DIFF = (
    "diff --git a/foo.py b/foo.py\n"
    "@@ -1,3 +1,4 @@\n"
    " context_line_1\n"   # line 1 (context)
    "+added_line_2\n"     # line 2 (added)
    " context_line_3\n"   # line 3 (context)
    " context_line_4\n"   # line 4 (context)
)

MULTI_FILE_DIFF = (
    "diff --git a/foo.py b/foo.py\n"
    "@@ -1,2 +1,3 @@\n"
    " line_1\n"            # foo.py line 1 (context)
    "+added_foo\n"         # foo.py line 2 (added)
    " line_3\n"            # foo.py line 3 (context)
    "diff --git a/bar.py b/bar.py\n"
    "@@ -1,1 +1,2 @@\n"
    " bar_line_1\n"        # bar.py line 1 (context)
    "+added_bar\n"         # bar.py line 2 (added)
)


class TestParseDiffChangedLines:
    def test_empty_diff_returns_empty_set(self) -> None:
        assert parse_diff_changed_lines("") == set()

    def test_added_line_is_included(self) -> None:
        result = parse_diff_changed_lines(SINGLE_FILE_DIFF)
        assert ("foo.py", 2) in result

    def test_context_line_is_included(self) -> None:
        """Context lines that exist in the new file must be included."""
        result = parse_diff_changed_lines(SINGLE_FILE_DIFF)
        assert ("foo.py", 1) in result
        assert ("foo.py", 3) in result
        assert ("foo.py", 4) in result

    def test_deleted_line_is_not_included(self) -> None:
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "@@ -1,2 +1,1 @@\n"
            "-deleted_line\n"
            " kept_line\n"
        )
        result = parse_diff_changed_lines(diff)
        # Only the kept context line should be present (line 1 in new file)
        assert ("foo.py", 1) in result
        # The deleted line maps to line 0 (before hunk start) — just assert it's small
        assert len(result) == 1

    def test_multi_file_diff_separates_files(self) -> None:
        result = parse_diff_changed_lines(MULTI_FILE_DIFF)
        # foo.py entries
        assert ("foo.py", 1) in result
        assert ("foo.py", 2) in result
        assert ("foo.py", 3) in result
        # bar.py entries
        assert ("bar.py", 1) in result
        assert ("bar.py", 2) in result
        # No cross-contamination
        assert ("foo.py", 99) not in result
        assert ("bar.py", 99) not in result

    def test_hunk_starting_at_non_one_line(self) -> None:
        """When a hunk starts at line 10, line numbers must be correct."""
        diff = (
            "diff --git a/baz.py b/baz.py\n"
            "@@ -10,3 +10,4 @@\n"
            " line_10\n"    # line 10
            "+new_line_11\n"  # line 11
            " line_12\n"    # line 12
            " line_13\n"    # line 13
        )
        result = parse_diff_changed_lines(diff)
        assert ("baz.py", 10) in result
        assert ("baz.py", 11) in result
        assert ("baz.py", 12) in result
        assert ("baz.py", 13) in result
        assert ("baz.py", 9) not in result
        assert ("baz.py", 14) not in result

    def test_returns_set_type(self) -> None:
        result = parse_diff_changed_lines(SINGLE_FILE_DIFF)
        assert isinstance(result, set)

    def test_no_duplicate_entries(self) -> None:
        """Each (file, line) pair must appear at most once (set semantics)."""
        result = parse_diff_changed_lines(SINGLE_FILE_DIFF)
        result_list = list(result)
        assert len(result_list) == len(set(result_list))

    def test_no_newline_marker_ignored(self) -> None:
        """Lines starting with '\\' (e.g. '\\ No newline at end of file') must be ignored."""
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "@@ -1,1 +1,1 @@\n"
            "+only_line\n"
            "\\ No newline at end of file\n"
        )
        result = parse_diff_changed_lines(diff)
        assert ("foo.py", 1) in result
        assert len(result) == 1
