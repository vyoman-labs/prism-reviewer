import os
import re
import subprocess
from typing import Dict, Any, List, Optional
from ..core.logger import get_logger

logger = get_logger("prism_reviewer.git_utils")


def run_git_command(repo_path: str, args: List[str]) -> str:
    """Helper to run a git command in the target repo_path directory."""
    if not os.path.isdir(repo_path):
        raise ValueError(f"Path is not a valid directory: {repo_path}")
    
    cmd = ["git"] + args
    logger.debug(f"Running command: {' '.join(cmd)} in {repo_path}")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            encoding="utf-8",
            errors="ignore"
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {' '.join(cmd)}. Stderr: {e.stderr}")
        raise RuntimeError(f"Git command failed: {e.stderr.strip()}") from e
    except FileNotFoundError as e:
        logger.error("git executable not found in PATH")
        raise RuntimeError("git executable not found in system PATH") from e


def get_git_diff(repo_path: str, base: str = "HEAD") -> str:
    """
    Retrieves the git diff comparing base to the working directory.
    If base is 'staged', gets the diff of staged changes.
    If base is 'unstaged', gets the diff of unstaged changes.
    Otherwise, compares base with HEAD or working tree.
    """
    try:
        if base == "staged":
            return run_git_command(repo_path, ["diff", "--cached"])
        elif base == "unstaged":
            return run_git_command(repo_path, ["diff"])
        else:
            return run_git_command(repo_path, ["diff", base])
    except Exception as e:
        logger.warning(f"Failed to get git diff for base '{base}': {e}")
        return ""


def get_repo_structure(repo_path: str) -> Dict[str, Any]:
    """
    Returns a nested directory tree representation of files tracked by git.
    """
    try:
        files_str = run_git_command(repo_path, ["ls-files"])
        files = [f.strip() for f in files_str.splitlines() if f.strip()]
        
        structure: Dict[str, Any] = {"name": os.path.basename(os.path.abspath(repo_path)), "type": "directory", "children": {}}
        
        for file in files:
            parts = file.split("/")
            current = structure
            for i, part in enumerate(parts):
                is_last = (i == len(parts) - 1)
                children = current["children"]
                if part not in children:
                    if is_last:
                        children[part] = {"name": part, "type": "file", "path": file}
                    else:
                        children[part] = {"name": part, "type": "directory", "children": {}}
                current = children[part]
                
        # Helper to convert children dict to list recursively
        def dict_to_list(node: Dict[str, Any]) -> Dict[str, Any]:
            if node["type"] == "directory":
                node["children"] = [dict_to_list(child) for child in node["children"].values()]
            return node
            
        return dict_to_list(structure)
    except Exception as e:
        logger.warning(f"Failed to get repo structure: {e}")
        return {"name": os.path.basename(os.path.abspath(repo_path)), "type": "directory", "children": []}


def get_file_content_at_commit(repo_path: str, file_path: str, commit: str = "HEAD") -> str:
    """
    Retrieves the content of a file at a specific git revision/commit.
    """
    # Normalize paths to use forward slashes for git show
    normalized_path = file_path.replace("\\", "/")
    try:
        return run_git_command(repo_path, ["show", f"{commit}:{normalized_path}"])
    except Exception as e:
        logger.warning(f"Failed to get file content for {file_path} at {commit}: {e}")
        return ""


def parse_diff_changed_lines(diff: str) -> set[tuple[str, int]]:
    """
    Parses a unified diff string and returns the set of (filename, line_number)
    pairs for all lines present in the *new* version of each file in the patch.

    Both added lines (starting with ``+``) and unchanged context lines
    (starting with a space) are included, because a finding may legitimately
    reference an unchanged line that is visible in the diff.  Deleted lines
    (starting with ``-``) are excluded because they no longer exist.

    This is a pure function — no file I/O, no side effects — so it is trivially
    unit-testable with crafted diff strings.

    Args:
        diff: Raw unified diff string (e.g., from ``git diff``).

    Returns:
        A set of ``(relative_file_path, line_number)`` tuples.  Line numbers
        are 1-indexed, matching the positions in the new version of the file.
    """
    result: set[tuple[str, int]] = set()
    current_file: str = ""
    new_line: int = 0

    for raw_line in diff.splitlines():
        if raw_line.startswith("diff --git "):
            # Extract the b/ path which is the new file name
            parts = raw_line.split(" b/", 1)
            current_file = parts[1].strip() if len(parts) == 2 else ""
            new_line = 0

        elif raw_line.startswith("@@ "):
            # Hunk header: @@ -old_start,old_count +new_start,new_count @@
            match = re.search(r"\+(\d+)", raw_line)
            new_line = int(match.group(1)) if match else 0

        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            # Added line — exists in the new file
            if current_file:
                result.add((current_file, new_line))
            new_line += 1

        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            # Deleted line — does not advance the new-file line counter
            pass

        # Context line — exists unchanged in the new file
        elif raw_line.startswith(" "):
            if current_file:
                result.add((current_file, new_line))
            new_line += 1

        # Lines starting with '\' (e.g. "\ No newline at end of file") are ignored

    return result


def split_diff_by_file(diff_content: str) -> List[Dict[str, Any]]:
    """
    Splits a unified diff string into a list of dictionaries, one per file.

    Args:
        diff_content: Raw unified diff string.

    Returns:
        List of dictionaries containing 'file' (str relative path) and
        'diff' (str unified diff for this file only).
    """
    if not diff_content.strip():
        return []
    
    files_diffs: List[Dict[str, Any]] = []
    lines = diff_content.splitlines(keepends=True)
    current_file: Optional[str] = None
    current_diff_lines: List[str] = []
    
    for line in lines:
        if line.startswith("diff --git "):
            if current_file is not None and current_diff_lines:
                files_diffs.append({
                    "file": current_file,
                    "diff": "".join(current_diff_lines)
                })
            current_diff_lines = [line]
            parts = line.split(" b/", 1)
            current_file = parts[1].strip() if len(parts) == 2 else "unknown"
        else:
            if current_file is not None:
                current_diff_lines.append(line)
                
    if current_file is not None and current_diff_lines:
        files_diffs.append({
            "file": current_file,
            "diff": "".join(current_diff_lines)
        })
        
    return files_diffs


def group_diffs_into_regions(
    files_diffs: List[Dict[str, Any]],
    max_lines: int,
) -> List[Dict[str, Any]]:
    """
    Groups file diffs into review regions such that each region contains
    at most max_lines of diff, unless a single file diff exceeds max_lines.

    Args:
        files_diffs: List of dictionaries returned by split_diff_by_file.
        max_lines: Max number of lines to group in one review region.

    Returns:
        List of region dictionaries. Each region contains:
        - files: List of relative paths in the region.
        - diff: Combined git diff string for files in the region.
        - line_count: Total lines in the diff.
        - region_index: 1-indexed index of the region.
        - total_regions: Total count of regions.
    """
    if not files_diffs:
        return []
        
    if max_lines <= 0:
        max_lines = 500
        
    regions: List[Dict[str, Any]] = []
    current_files: List[str] = []
    current_diff_parts: List[str] = []
    current_line_count = 0
    
    for fd in files_diffs:
        fd_diff: str = fd["diff"]
        fd_lines = fd_diff.count("\n")
        
        # If adding the next file exceeds max_lines, and the current region is not empty, flush
        if current_line_count > 0 and current_line_count + fd_lines > max_lines:
            regions.append({
                "files": current_files,
                "diff": "".join(current_diff_parts),
                "line_count": current_line_count,
            })
            current_files = []
            current_diff_parts = []
            current_line_count = 0
            
        current_files.append(fd["file"])
        current_diff_parts.append(fd_diff)
        current_line_count += fd_lines
        
    if current_files:
        regions.append({
            "files": current_files,
            "diff": "".join(current_diff_parts),
            "line_count": current_line_count,
        })
        
    # Add metadata to regions
    total = len(regions)
    for i, r in enumerate(regions):
        r["region_index"] = i + 1
        r["total_regions"] = total
        
    return regions
