"""Tests for the agents/prompts.py loader and all four Markdown prompt files."""

import pytest

from prism_reviewer.agents.prompts import (
    ARCHITECT_SYSTEM_PROMPT,
    INSPECTOR_SYSTEM_PROMPT,
    OUTPUT_SCHEMA_BLOCK,
    WARDEN_SYSTEM_PROMPT,
)


def test_all_prompts_are_non_empty() -> None:
    """Every prompt constant must load as a non-empty string."""
    for name, content in [
        ("WARDEN_SYSTEM_PROMPT", WARDEN_SYSTEM_PROMPT),
        ("ARCHITECT_SYSTEM_PROMPT", ARCHITECT_SYSTEM_PROMPT),
        ("INSPECTOR_SYSTEM_PROMPT", INSPECTOR_SYSTEM_PROMPT),
        ("OUTPUT_SCHEMA_BLOCK", OUTPUT_SCHEMA_BLOCK),
    ]:
        assert isinstance(content, str), f"{name} must be a str"
        assert len(content.strip()) > 0, f"{name} must not be empty"


def test_warden_prompt_contains_security_keywords() -> None:
    """Warden prompt must reference core security concepts."""
    for keyword in ("CRITICAL", "injection", "secret"):
        assert keyword.lower() in WARDEN_SYSTEM_PROMPT.lower(), (
            f"WARDEN_SYSTEM_PROMPT must contain '{keyword}'"
        )


def test_architect_prompt_contains_architecture_keywords() -> None:
    """Architect prompt must reference core structural concepts."""
    for keyword in ("N+1", "memory", "SOLID"):
        assert keyword.lower() in ARCHITECT_SYSTEM_PROMPT.lower(), (
            f"ARCHITECT_SYSTEM_PROMPT must contain '{keyword}'"
        )


def test_inspector_prompt_contains_logic_keywords() -> None:
    """Inspector prompt must reference core clean-code concepts."""
    for keyword in ("null", "except", "edge"):
        assert keyword.lower() in INSPECTOR_SYSTEM_PROMPT.lower(), (
            f"INSPECTOR_SYSTEM_PROMPT must contain '{keyword}'"
        )


def test_output_schema_contains_all_required_fields() -> None:
    """Output schema block must define all five required JSON fields."""
    for field in ("file", "line", "severity", "agent", "message"):
        assert field in OUTPUT_SCHEMA_BLOCK, (
            f"OUTPUT_SCHEMA_BLOCK must mention field '{field}'"
        )


def test_output_schema_mentions_severity_values() -> None:
    """Output schema must name all three severity levels."""
    for level in ("CRITICAL", "MAJOR", "ADVISORY"):
        assert level in OUTPUT_SCHEMA_BLOCK, (
            f"OUTPUT_SCHEMA_BLOCK must mention severity '{level}'"
        )
