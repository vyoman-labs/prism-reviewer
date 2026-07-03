import hashlib
import os
from typing import Optional

from ..core.logger import get_logger

logger = get_logger("prism_reviewer.utils.signature")


def get_finding_signature(
    repo_path: str,
    file_path: str,
    line_number: int,
    agent_name: str,
) -> str:
    """
    Calculates a unique content hash signature for a code-block finding.

    Reads a 5-line window of source context centred on ``line_number`` to
    capture the state of the code at that location.  The hash is therefore
    sensitive to both the location *and* the surrounding content, which means
    the same finding on genuinely changed code will receive a new signature and
    will not be suppressed by the idempotent deduplication filter.

    Args:
        repo_path: Absolute path to the repository root.
        file_path: Relative path of the file (as it appears in the diff).
        line_number: 1-indexed line number of the finding.
        agent_name: Name of the agent that produced the finding.

    Returns:
        The SHA-256 hex digest of the normalised finding content signature.
    """
    diff_context = _read_line_context(repo_path, file_path, line_number)
    # Normalise path separator so signatures are platform-independent
    normalized_path = file_path.replace("\\", "/")
    sig_input = f"{normalized_path}:{line_number}:{agent_name}:{diff_context}"
    return hashlib.sha256(sig_input.encode("utf-8")).hexdigest()


def _read_line_context(repo_path: str, file_path: str, line_number: int) -> str:
    """
    Returns a 5-line window of source text centred on ``line_number``.

    Returns an empty string if the file cannot be read or the line does not
    exist, so the signature still encodes the location even without content.

    Args:
        repo_path: Absolute path to the repository root.
        file_path: Relative path of the file.
        line_number: 1-indexed line number.

    Returns:
        A stripped, multi-line string of context lines, or an empty string.
    """
    full_path = os.path.join(repo_path, file_path)
    if not os.path.isfile(full_path):
        return ""
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        idx = line_number - 1
        if 0 <= idx < len(lines):
            start = max(0, idx - 2)
            end = min(len(lines), idx + 3)
            return "".join(lines[start:end]).strip()
    except Exception as exc:
        logger.warning(f"Failed to read context for {file_path}:{line_number}: {exc}")
    return ""
