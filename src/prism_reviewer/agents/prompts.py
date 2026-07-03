"""
prism_reviewer.agents.prompts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Thin loader that reads persona prompt Markdown files from the ``prompts/``
subdirectory and exposes them as typed string constants.

**No prompt strings are hardcoded in Python.**  All content lives in the
``.md`` files, so persona prompts can be edited without touching source code.

The files are read once at import time.  Any ``IOError`` during loading will
propagate immediately, making misconfiguration fail loudly at startup rather
than silently at review time.

Constants
---------
WARDEN_SYSTEM_PROMPT    System persona for the Warden (security) agent.
ARCHITECT_SYSTEM_PROMPT System persona for the Architect (structure) agent.
INSPECTOR_SYSTEM_PROMPT System persona for the Inspector (logic) agent.
OUTPUT_SCHEMA_BLOCK     Shared JSON output contract appended to every user turn.
"""

from pathlib import Path


def _load(filename: str) -> str:
    """
    Reads a prompt Markdown file from the ``prompts/`` subdirectory.

    Args:
        filename: Basename of the ``.md`` file (e.g. ``"warden.md"``).

    Returns:
        The full text content of the file as a string.

    Raises:
        FileNotFoundError: If the file does not exist at the expected path.
        IOError: If the file cannot be read.
    """
    path = Path(__file__).parent / "prompts" / filename
    return path.read_text(encoding="utf-8")


WARDEN_SYSTEM_PROMPT: str = _load("warden.md")
ARCHITECT_SYSTEM_PROMPT: str = _load("architect.md")
INSPECTOR_SYSTEM_PROMPT: str = _load("inspector.md")
OUTPUT_SCHEMA_BLOCK: str = _load("output_schema.md")
