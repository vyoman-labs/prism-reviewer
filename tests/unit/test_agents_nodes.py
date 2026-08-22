import os
import json
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest

from prism_reviewer.agents.state import Finding, ReviewState


@pytest.fixture(autouse=True)
def set_model_env() -> Generator[None, None, None]:
    """Ensures LLM_MODEL is set for agent node tests."""
    old = os.environ.get("LLM_MODEL")
    os.environ["LLM_MODEL"] = "test-agent-model"
    yield
    if old is None:
        os.environ.pop("LLM_MODEL", None)
    else:
        os.environ["LLM_MODEL"] = old


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
        "readme_content": "",
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
    """Returns valid JSON matching Finding structure."""
    return json.dumps({
        "findings": [
            {
                "id": f"{agent}-001",
                "file_path": "foo.py",
                "line_number": 2,
                "category": "security" if agent == "warden" else "architecture",
                "severity": "MEDIUM",
                "title": f"Sample Finding from {agent}",
                "description": "Something potentially wrong here.",
                "suggestion": "Fix it this way.",
                "confidence": "HIGH",
            }
        ]
    })


def _patch_llm(mock_response: str) -> Any:
    """Helper to patch litellm.completion."""
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = mock_response
    return patch("litellm.completion", return_value=mock_resp)


def _call_warden(state: ReviewState) -> dict:
    from prism_reviewer.agents.nodes import warden_node
    return warden_node(state)


def _call_architect(state: ReviewState) -> dict:
    from prism_reviewer.agents.nodes import architect_node
    return architect_node(state)


def _call_inspector(state: ReviewState) -> dict:
    from prism_reviewer.agents.nodes import inspector_node
    return inspector_node(state)


def _call_verifier(state: ReviewState) -> dict:
    from prism_reviewer.agents.nodes import verifier_node
    return verifier_node(state)


# ---------------------------------------------------------------------------
# Warden node
# ---------------------------------------------------------------------------

class TestWardenNode:
    def test_warden_unconfigured_model_raises_value_error(self, tmp_path: Any) -> None:
        """warden_node must raise ValueError if no model is configured."""
        from prism_reviewer.core.config import config
        empty_toml = tmp_path / "empty.toml"
        empty_toml.write_text("[llm]\napi_key=''\nmodel=''\n", encoding="utf-8")
        for key in ["LLM_MODEL", "WARDEN_MODEL_OVERRIDE", "ARCHITECT_MODEL_OVERRIDE", "INSPECTOR_MODEL_OVERRIDE", "VERIFIER_MODEL_OVERRIDE"]:
            os.environ.pop(key, None)
        config.reset_for_testing(str(empty_toml))
        try:
            state = _make_state()
            with pytest.raises(ValueError, match="No LLM model configured for agent 'warden'"):
                _call_warden(state)
        finally:
            os.environ["LLM_MODEL"] = "test-agent-model"
            config.reset_for_testing()

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
            "## Repository README",
            "## Git Diff",
            "## Dependency Analysis",
            "## Code Symbol Map",
        ):
            assert section in user_msg["content"], f"Missing section: {section}"

    def test_warden_passes_reasoning_effort_override(self) -> None:
        """warden_node must pass high reasoning_effort to completion_with_retry by default."""
        state = _make_state()
        with patch(
            "prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry",
            return_value=_advisory_finding_json("warden"),
        ) as mock_call:
            _call_warden(state)
        call_kwargs = mock_call.call_args[1]
        assert call_kwargs.get("reasoning_effort") == "high"

    def test_warden_skips_when_diff_is_only_test_files(self) -> None:
        """warden_node must return empty findings without calling LLM if diff contains only test files."""
        test_only_diff = (
            "diff --git a/tests/test_foo.py b/tests/test_foo.py\n"
            "@@ -1,2 +1,3 @@\n"
            " line_1\n"
            "+added_line\n"
            " line_3\n"
        )
        state = _make_state(git_diff=test_only_diff)
        with patch("prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry") as mock_call:
            result = _call_warden(state)
        mock_call.assert_not_called()
        assert result["raw_findings"] == []

    def test_warden_filters_out_test_files_in_mixed_diff(self) -> None:
        """warden_node must exclude test files from the diff passed to the LLM."""
        mixed_diff = (
            "diff --git a/src/main.py b/src/main.py\n"
            "@@ -1,2 +1,3 @@\n"
            " line_1\n"
            "+added_main\n"
            " line_3\n"
            "diff --git a/tests/test_main.py b/tests/test_main.py\n"
            "@@ -1,2 +1,3 @@\n"
            " test_line_1\n"
            "+added_test\n"
            " test_line_3\n"
        )
        state = _make_state(git_diff=mixed_diff)
        with patch(
            "prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry",
            return_value=_advisory_finding_json("warden"),
        ) as mock_call:
            _call_warden(state)
        messages = mock_call.call_args[0][0]
        user_turn_content = messages[1]["content"]
        assert "src/main.py" in user_turn_content
        assert "tests/test_main.py" not in user_turn_content

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


class TestPromptCachingAndTokenLogging:
    def test_build_user_turn_prompt_caching_order(self) -> None:
        """Verify static shared context comes before dynamic PR title and git diff for prompt caching."""
        from prism_reviewer.agents.nodes import _build_user_turn
        state = _make_state(
            pr_title="PR Title Dynamic",
            git_diff="diff --git a/a.py b/a.py",
            repo_structure="a.py",
        )
        prompt = _build_user_turn(state, "warden")

        repo_struct_idx = prompt.find("## Repository Structure")
        codelens_dep_idx = prompt.find("## Dependency Analysis")
        codelens_search_idx = prompt.find("## Code Search Hits")
        codelens_ast_idx = prompt.find("## Code Symbol Map")
        readme_idx = prompt.find("## Repository README")
        pr_ctx_idx = prompt.find("## Pull Request Context")
        git_diff_idx = prompt.find("## Git Diff")

        assert repo_struct_idx != -1
        assert codelens_dep_idx != -1
        assert codelens_search_idx != -1
        assert codelens_ast_idx != -1
        assert readme_idx != -1
        assert pr_ctx_idx != -1
        assert git_diff_idx != -1

        # All static sections must come BEFORE dynamic PR Context and Git Diff
        assert repo_struct_idx < pr_ctx_idx
        assert codelens_dep_idx < pr_ctx_idx
        assert codelens_search_idx < pr_ctx_idx
        assert codelens_ast_idx < pr_ctx_idx
        assert readme_idx < pr_ctx_idx
        assert pr_ctx_idx < git_diff_idx

    def test_build_user_turn_includes_pr_comments(self) -> None:
        """Verify _build_user_turn includes Prior Review Comments section when pr_comments is present."""
        from prism_reviewer.agents.nodes import _build_user_turn
        state = _make_state(
            pr_comments="- **Inline Review on `main.py:10` [CRITICAL]**: Fix memory leak",
        )
        prompt = _build_user_turn(state, "warden")
        assert "## Prior Review Comments & Discussion" in prompt
        assert "Fix memory leak" in prompt

    def test_codelens_max_search_files_cap_defaults_to_25(self) -> None:
        """Verify build_context_node uses Config.codelens_max_search_files (25)."""
        from prism_reviewer.core.config import Config
        assert Config.codelens_max_search_files() == 25


class TestParseFindings:
    def test_parse_findings_forces_advisory_on_test_files(self) -> None:
        """_parse_findings must override CRITICAL or MAJOR to ADVISORY for test files."""
        from prism_reviewer.agents.nodes import NodeLogger, _parse_findings
        mock_logger = MagicMock()
        node_log = NodeLogger(mock_logger, "TEST Node")

        raw_response = json.dumps({
            "findings": [
                {
                    "file": "tests/test_service.py",
                    "line": 10,
                    "severity": "CRITICAL",
                    "message": "Critical issue in test code",
                },
                {
                    "file": "src/service.py",
                    "line": 20,
                    "severity": "CRITICAL",
                    "message": "Critical issue in main code",
                },
            ]
        })

        findings = _parse_findings(raw_response, "warden", "/tmp/repo", node_log)
        assert len(findings) == 2
        test_finding = next(f for f in findings if f["file"] == "tests/test_service.py")
        src_finding = next(f for f in findings if f["file"] == "src/service.py")

        assert test_finding["severity"] == "ADVISORY"
        assert src_finding["severity"] == "CRITICAL"


