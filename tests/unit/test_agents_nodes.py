"""Tests for the three agent nodes (warden, architect, inspector)."""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from prism_reviewer.agents.state import Finding, ReviewState


def _make_state(**overrides: Any) -> ReviewState:
    """Returns a minimal ReviewState suitable for unit tests."""
    base: ReviewState = {
        "repo_path": "/tmp/test_repo",
        "git_diff": "diff --git a/foo.py b/foo.py\n@@ -1,3 +1,4 @@\n context\n+new_line\n context2\n",
        "pr_title": "Test PR",
        "pr_description": "A test pull request",
        "repo_structure": "foo.py",
        "ast_map": {},
        "codelens_dep_summary": "(no manifests found)",
        "codelens_search_hits": "(no hits)",
        "context_content": "",
        "rules_content": "",
        "previous_signatures": [],
        "regions": [],
        "raw_findings": [],
        "verified_findings": [],
        "report_markdown": "",
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def _advisory_finding_json(agent: str = "warden") -> str:
    """Returns a valid JSON findings response using ADVISORY severity only."""
    return json.dumps({
        "findings": [
            {
                "file": "foo.py",
                "line": 2,
                "severity": "ADVISORY",
                "agent": agent,
                "message": "Test finding from fixture",
            }
        ]
    })


def _patch_llm(return_value: str):
    """Returns a patch context manager for ResilientLLMClient.completion_with_retry."""
    return patch(
        "prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry",
        return_value=return_value,
    )


# ---------------------------------------------------------------------------
# Warden node
# ---------------------------------------------------------------------------

class TestWardenNode:
    def test_warden_returns_raw_findings_key(self) -> None:
        """warden_node must return a dict with 'raw_findings'."""
        state = _make_state()
        with _patch_llm(_advisory_finding_json("warden")):
            result = _call_warden(state)
        assert "raw_findings" in result

    def test_warden_stamps_correct_agent_name(self) -> None:
        """Every finding from warden_node must have agent='warden'."""
        state = _make_state()
        with _patch_llm(_advisory_finding_json("warden")):
            result = _call_warden(state)
        for finding in result["raw_findings"]:
            assert finding["agent"] == "warden"

    def test_warden_uses_warden_system_prompt(self) -> None:
        """warden_node must pass WARDEN_SYSTEM_PROMPT as the system role message."""
        from prism_reviewer.agents.prompts import WARDEN_SYSTEM_PROMPT
        state = _make_state()
        with patch(
            "prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry",
            return_value=_advisory_finding_json("warden"),
        ) as mock_call:
            _call_warden(state)
        call_args = mock_call.call_args
        messages = call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert system_msg["content"] == WARDEN_SYSTEM_PROMPT

    def test_warden_user_turn_contains_required_sections(self) -> None:
        """The user-turn assembled for warden must contain all labeled context sections."""
        state = _make_state()
        with patch(
            "prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry",
            return_value=_advisory_finding_json("warden"),
        ) as mock_call:
            _call_warden(state)
        messages = mock_call.call_args[0][0]
        user_msg = next(m for m in messages if m["role"] == "user")
        for section in (
            "## Pull Request Context",
            "## Git Diff",
            "## Dependency Analysis",
            "## Code Symbol Map",
        ):
            assert section in user_msg["content"], f"Missing section: {section}"

    def test_warden_passes_reasoning_effort_override(self) -> None:
        """warden_node must forward the per-agent reasoning_effort to completion_with_retry."""
        state = _make_state()
        with patch(
            "prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry",
            return_value=_advisory_finding_json("warden"),
        ) as mock_call:
            _call_warden(state)
        # reasoning_effort is passed as a keyword argument
        call_kwargs = mock_call.call_args[1]
        assert "reasoning_effort" in call_kwargs

    def test_warden_graceful_on_empty_findings(self) -> None:
        """warden_node must return an empty list when the LLM returns no findings."""
        state = _make_state()
        with _patch_llm(json.dumps({"findings": []})):
            result = _call_warden(state)
        assert result["raw_findings"] == []

    def test_warden_graceful_on_malformed_json(self) -> None:
        """warden_node must return an empty list when the LLM returns malformed JSON."""
        state = _make_state()
        with _patch_llm("not valid json {{{{"):
            result = _call_warden(state)
        assert result["raw_findings"] == []

    def test_warden_stamps_signature(self) -> None:
        """Every finding returned by warden_node must have a non-empty signature."""
        state = _make_state()
        with _patch_llm(_advisory_finding_json("warden")):
            result = _call_warden(state)
        for finding in result["raw_findings"]:
            assert finding.get("signature"), "Each finding must have a signature"


# ---------------------------------------------------------------------------
# Architect node
# ---------------------------------------------------------------------------

class TestArchitectNode:
    def test_architect_stamps_correct_agent_name(self) -> None:
        from prism_reviewer.agents.nodes import architect_node
        state = _make_state()
        with _patch_llm(_advisory_finding_json("architect")):
            result = architect_node(state)
        for finding in result["raw_findings"]:
            assert finding["agent"] == "architect"

    def test_architect_uses_architect_system_prompt(self) -> None:
        from prism_reviewer.agents.nodes import architect_node
        from prism_reviewer.agents.prompts import ARCHITECT_SYSTEM_PROMPT
        state = _make_state()
        with patch(
            "prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry",
            return_value=_advisory_finding_json("architect"),
        ) as mock_call:
            architect_node(state)
        messages = mock_call.call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert system_msg["content"] == ARCHITECT_SYSTEM_PROMPT

    def test_architect_graceful_on_malformed_json(self) -> None:
        from prism_reviewer.agents.nodes import architect_node
        state = _make_state()
        with _patch_llm("garbage output"):
            result = architect_node(state)
        assert result["raw_findings"] == []


# ---------------------------------------------------------------------------
# Inspector node
# ---------------------------------------------------------------------------

class TestInspectorNode:
    def test_inspector_stamps_correct_agent_name(self) -> None:
        from prism_reviewer.agents.nodes import inspector_node
        state = _make_state()
        with _patch_llm(_advisory_finding_json("inspector")):
            result = inspector_node(state)
        for finding in result["raw_findings"]:
            assert finding["agent"] == "inspector"

    def test_inspector_graceful_on_malformed_json(self) -> None:
        from prism_reviewer.agents.nodes import inspector_node
        state = _make_state()
        with _patch_llm(""):
            result = inspector_node(state)
        assert result["raw_findings"] == []


# ---------------------------------------------------------------------------
# NodeLogger
# ---------------------------------------------------------------------------

class TestNodeLogger:
    def test_flush_emits_exactly_one_log_call(self) -> None:
        """NodeLogger.flush() must emit exactly one logger.info() call."""
        from prism_reviewer.agents.nodes import NodeLogger
        mock_logger = MagicMock()
        nl = NodeLogger(mock_logger, "TEST Node")
        nl.record("step one")
        nl.record("step two")
        nl.flush()
        assert mock_logger.info.call_count == 1

    def test_flush_block_contains_recorded_messages(self) -> None:
        """The flushed block must contain all recorded messages."""
        from prism_reviewer.agents.nodes import NodeLogger
        mock_logger = MagicMock()
        nl = NodeLogger(mock_logger, "TEST Node")
        nl.record("alpha message")
        nl.record("beta message")
        nl.flush()
        block = mock_logger.info.call_args[0][0]
        assert "alpha message" in block
        assert "beta message" in block

    def test_flush_block_contains_total_time(self) -> None:
        """The flushed block footer must contain 'Total:'."""
        from prism_reviewer.agents.nodes import NodeLogger
        mock_logger = MagicMock()
        nl = NodeLogger(mock_logger, "TEST Node")
        nl.flush()
        block = mock_logger.info.call_args[0][0]
        assert "Total:" in block


# ---------------------------------------------------------------------------
# Helpers (call through the real function with mock LLM)
# ---------------------------------------------------------------------------

def _call_warden(state: ReviewState) -> dict:
    from prism_reviewer.agents.nodes import warden_node
    return warden_node(state)
