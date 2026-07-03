"""Unit tests for split_diff_by_file and group_diffs_into_regions in utils/git_utils.py."""

from typing import Any, Dict, List
import pytest

from prism_reviewer.utils.git_utils import split_diff_by_file, group_diffs_into_regions


def test_split_diff_by_file_empty() -> None:
    assert split_diff_by_file("") == []
    assert split_diff_by_file("   ") == []


def test_split_diff_by_file_single() -> None:
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "index 12345..67890 100644\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " context\n"
        "+new_line\n"
    )
    result = split_diff_by_file(diff)
    assert len(result) == 1
    assert result[0]["file"] == "foo.py"
    assert result[0]["diff"] == diff


def test_split_diff_by_file_multiple() -> None:
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "--- a/foo.py\n"
        "+++ b/foo.py\n"
        "@@ -1,2 +1,2 @@\n"
        " context\n"
        "+new_line\n"
        "diff --git a/bar.py b/bar.py\n"
        "--- a/bar.py\n"
        "+++ b/bar.py\n"
        "@@ -1,2 +1,2 @@\n"
        " old_bar\n"
        "+new_bar\n"
    )
    result = split_diff_by_file(diff)
    assert len(result) == 2
    assert result[0]["file"] == "foo.py"
    assert "foo.py" in result[0]["diff"]
    assert "bar.py" not in result[0]["diff"]
    
    assert result[1]["file"] == "bar.py"
    assert "bar.py" in result[1]["diff"]
    assert "foo.py" not in result[1]["diff"]


def test_group_diffs_into_regions_empty() -> None:
    assert group_diffs_into_regions([], 500) == []


def test_group_diffs_into_regions_single_fits() -> None:
    files_diffs = [
        {"file": "foo.py", "diff": "line1\nline2\n"},
        {"file": "bar.py", "diff": "line1\nline2\nline3\n"}
    ]
    regions = group_diffs_into_regions(files_diffs, 10)
    assert len(regions) == 1
    assert regions[0]["files"] == ["foo.py", "bar.py"]
    assert regions[0]["line_count"] == 5
    assert regions[0]["region_index"] == 1
    assert regions[0]["total_regions"] == 1


def test_group_diffs_into_regions_split() -> None:
    files_diffs = [
        {"file": "foo.py", "diff": "line1\nline2\nline3\nline4\n"},
        {"file": "bar.py", "diff": "line1\nline2\nline3\nline4\n"},
        {"file": "baz.py", "diff": "line1\nline2\n"}
    ]
    regions = group_diffs_into_regions(files_diffs, 5)
    assert len(regions) == 3
    
    assert regions[0]["files"] == ["foo.py"]
    assert regions[0]["region_index"] == 1
    
    assert regions[1]["files"] == ["bar.py"]
    assert regions[1]["region_index"] == 2
    
    assert regions[2]["files"] == ["baz.py"]
    assert regions[2]["region_index"] == 3
    
    for r in regions:
        assert r["total_regions"] == 3


def test_group_diffs_into_regions_giant_file() -> None:
    files_diffs = [
        {"file": "huge.py", "diff": "\n" * 20},
        {"file": "small.py", "diff": "\n" * 2}
    ]
    regions = group_diffs_into_regions(files_diffs, 5)
    assert len(regions) == 2
    assert regions[0]["files"] == ["huge.py"]
    assert regions[1]["files"] == ["small.py"]
