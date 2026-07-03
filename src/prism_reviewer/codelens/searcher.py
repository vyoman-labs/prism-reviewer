import os
import re
from typing import Dict, Any, List, Optional
from ..core.logger import get_logger
from .parser import UniversalASTAnalyzer

logger = get_logger("prism_reviewer.codelens.searcher")


def is_ignored(path: str) -> bool:
    """Helper to check if directory/file should be ignored during searches."""
    ignored_parts = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".egg-info"
    }
    parts = os.path.normpath(path).split(os.sep)
    return any(p in ignored_parts for p in parts)


def find_text(repo_path: str, query: str, extension_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Performs a line-by-line text/regex search across the repo files.
    """
    results = []
    try:
        rx = re.compile(query, re.IGNORECASE)
    except re.error as e:
        logger.warning(f"Invalid regex query: {query}. Error: {e}")
        return []

    try:
        for root, dirs, files in os.walk(repo_path):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if not is_ignored(os.path.join(root, d))]
            
            for file in files:
                file_path = os.path.join(root, file)
                if is_ignored(file_path):
                    continue
                    
                _, ext = os.path.splitext(file)
                if extension_filter and ext.lower() not in [e.lower() for e in extension_filter]:
                    continue
                    
                relative_path = os.path.relpath(file_path, repo_path)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if rx.search(line):
                                results.append({
                                    "file": relative_path.replace("\\", "/"),
                                    "line_number": line_num,
                                    "content": line.strip()
                                })
                                if len(results) >= 500: # Safety cap
                                    return results
                except Exception as e:
                    logger.debug(f"Could not read {file_path} for search: {e}")
    except Exception as e:
        logger.warning(f"Failed performing search in {repo_path}: {e}")
        
    return results


def get_full_file(repo_path: str, file_path: str) -> str:
    """Reads and returns the full content of a file from the repository."""
    try:
        full_path = os.path.abspath(os.path.join(repo_path, file_path))
        # Safety check to ensure target file is inside repository directory
        abs_repo = os.path.abspath(repo_path)
        if not full_path.startswith(abs_repo):
            raise PermissionError("Access denied: file path lies outside repository root.")
            
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {file_path}")
            
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        logger.warning(f"Failed to read file content for {file_path}: {e}")
        return ""


def get_related_files(repo_path: str, target_file: str) -> List[str]:
    """
    Finds files related to target_file based on name, imports, and proximity.
    """
    related = set()
    try:
        base_name = os.path.basename(target_file)
        name_no_ext, ext = os.path.splitext(base_name)
        
        # 1. Proximity: Other files in the same directory
        target_dir = os.path.dirname(os.path.abspath(os.path.join(repo_path, target_file)))
        if os.path.isdir(target_dir):
            for f in os.listdir(target_dir):
                f_path = os.path.join(target_dir, f)
                if os.path.isfile(f_path) and f != base_name:
                    rel = os.path.relpath(f_path, repo_path).replace("\\", "/")
                    if not is_ignored(rel):
                        related.add(rel)
                        
        # 2. Name matching: E.g., target 'foo.py' matches 'test_foo.py' or 'foo_helper.py'
        # Look for files containing name_no_ext in their filename
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not is_ignored(os.path.join(root, d))]
            for file in files:
                if name_no_ext in file and file != base_name:
                    rel = os.path.relpath(os.path.join(root, file), repo_path).replace("\\", "/")
                    if not is_ignored(rel):
                        related.add(rel)
 
        # 3. Usage/Import Search: Files importing/referencing the module name
        # Clean name_no_ext for use in imports (e.g. replacing hyphens/underscores if Python/JS)
        search_query = rf"\b{re.escape(name_no_ext)}\b"
        usages = find_text(repo_path, search_query)
        for usage in usages:
            if usage["file"] != target_file.replace("\\", "/"):
                related.add(usage["file"])
    except Exception as e:
        logger.warning(f"Failed to get related files for {target_file}: {e}")
            
    return sorted(list(related))[:20]  # Limit to top 20 related files


def get_file_methods(repo_path: str, file_path: str) -> Dict[str, Any]:
    """
    Extracts high-level symbols/methods from a file using UniversalASTAnalyzer.
    """
    try:
        full_path = os.path.abspath(os.path.join(repo_path, file_path))
        # Safety check to ensure target file is inside repository directory
        abs_repo = os.path.abspath(repo_path)
        if not full_path.startswith(abs_repo):
            raise PermissionError("Access denied: file path lies outside repository root.")
            
        analyzer = UniversalASTAnalyzer()
        return analyzer.get_ast_skeleton(full_path)
    except Exception as e:
        logger.warning(f"Failed to get file methods for {file_path}: {e}")
        return {"file_path": file_path, "mode": "error", "symbols": []}
