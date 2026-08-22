"""Integration tests for the LangGraph review pipeline graph."""

import json
from unittest.mock import MagicMock, patch
import pytest

from prism_reviewer.agents.graph import build_graph
from prism_reviewer.agents.state import ReviewState


def _make_state() -> ReviewState:
    diff = (
        "diff --git a/foo.py b/foo.py\n"
        "@@ -1,3 +1,4 @@\n"
        " context\n"
        "+new_line\n"
        " context2\n"
    )
    return {
        "repo_path": "/tmp/test_repo",
        "git_diff": diff,
        "pr_title": "Test PR",
        "pr_description": "PR Description",
        "repo_structure": "foo.py",
        "ast_map": {},
        "codelens_dep_summary": "",
        "codelens_search_hits": "",
        "context_content": "",
        "rules_content": "",
        "previous_signatures": [],
        "regions": [],
        "raw_findings": [],
        "verified_findings": [],
        "report_markdown": "",
    }


def _mock_agent_response(agent_name: str) -> str:
    """Returns a valid JSON response with ADVISORY-only severity."""
    return json.dumps({
        "findings": [
            {
                "file": "foo.py",
                "line": 2,
                "severity": "ADVISORY",
                "agent": agent_name,
                "message": f"Finding from {agent_name}",
            }
        ]
    })


class TestAgentsGraph:
    @patch("prism_reviewer.agents.nodes._get_repo_structure", return_value="foo.py")
    @patch("prism_reviewer.agents.nodes.UniversalASTAnalyzer")
    @patch("prism_reviewer.agents.nodes.scan_dependencies", return_value=[])
    @patch("prism_reviewer.agents.nodes.find_text", return_value=[])
    @patch("os.path.isfile", return_value=True)
    @patch("prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry")
    def test_full_graph_execution(
        self,
        mock_completion,
        mock_isfile,
        mock_find_text,
        mock_scan_deps,
        mock_ast_analyzer_class,
        mock_get_repo_structure,
    ) -> None:
        """The compiled graph correctly runs build_context, runs agents in parallel, verifies findings, and aggregates report."""
        # Setup mock AST analyzer
        mock_analyzer = MagicMock()
        mock_analyzer.get_ast_skeleton.return_value = {"symbols": []}
        mock_ast_analyzer_class.return_value = mock_analyzer

        # We have three parallel agents: warden, architect, inspector.
        # completion_with_retry will be called three times, once for each agent.
        # We return a unique ADVISORY finding for each agent.
        mock_completion.side_effect = [
            _mock_agent_response("warden"),
            _mock_agent_response("architect"),
            _mock_agent_response("inspector"),
        ]

        state = _make_state()
        graph = build_graph()
        
        # Invoke graph
        final_state = graph.invoke(state)

        # Assertions
        assert "raw_findings" in final_state
        assert len(final_state["raw_findings"]) == 3
        
        # Verifier checks: line 2 exists in git_diff, so all 3 pass verification
        assert "verified_findings" in final_state
        assert len(final_state["verified_findings"]) == 3

        # Report contains findings from all three
        assert "report_markdown" in final_state
        report = final_state["report_markdown"]
        assert "Vyoman Labs | 🌈 Prism Reviewer AI Code Review Report" in report
        assert "warden" in report
        assert "architect" in report
        assert "inspector" in report
        assert "Total: " not in report  # NodeLogger Total suffix should be in logs, not the final report

    @patch("prism_reviewer.agents.nodes._get_repo_structure", return_value="foo.py")
    @patch("prism_reviewer.agents.nodes.UniversalASTAnalyzer")
    @patch("prism_reviewer.agents.nodes.scan_dependencies", return_value=[])
    @patch("prism_reviewer.agents.nodes.find_text", return_value=[])
    @patch("os.path.isfile", return_value=True)
    @patch("prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry")
    def test_graph_stream_events(
        self,
        mock_completion,
        mock_isfile,
        mock_find_text,
        mock_scan_deps,
        mock_ast_analyzer_class,
        mock_get_repo_structure,
    ) -> None:
        """Streaming the graph emits events sequentially as each node completes."""
        mock_analyzer = MagicMock()
        mock_analyzer.get_ast_skeleton.return_value = {"symbols": []}
        mock_ast_analyzer_class.return_value = mock_analyzer

        mock_completion.side_effect = [
            _mock_agent_response("warden"),
            _mock_agent_response("architect"),
            _mock_agent_response("inspector"),
        ]

        state = _make_state()
        graph = build_graph()

        completed_nodes = []
        for event in graph.stream(state, stream_mode="updates"):
            for node_name in event:
                completed_nodes.append(node_name)

        # Confirm all nodes completed in correct lifecycle order
        # build_context -> [warden, architect, inspector] (parallel order can vary) -> verifier -> aggregator
        assert "build_context" in completed_nodes
        assert "warden" in completed_nodes
        assert "architect" in completed_nodes
        assert "inspector" in completed_nodes
        assert "verifier" in completed_nodes
        assert "aggregator" in completed_nodes

        # verifier should execute after all three agents
        build_idx = completed_nodes.index("build_context")
        warden_idx = completed_nodes.index("warden")
        arch_idx = completed_nodes.index("architect")
        insp_idx = completed_nodes.index("inspector")
        verifier_idx = completed_nodes.index("verifier")
        aggregator_idx = completed_nodes.index("aggregator")

        assert build_idx < warden_idx
        assert build_idx < arch_idx
        assert build_idx < insp_idx
        assert warden_idx < verifier_idx
        assert arch_idx < verifier_idx
        assert insp_idx < verifier_idx
        assert verifier_idx < aggregator_idx

    @patch("prism_reviewer.agents.nodes._get_repo_structure", return_value="foo.py\nbar.py")
    @patch("prism_reviewer.agents.nodes.UniversalASTAnalyzer")
    @patch("prism_reviewer.agents.nodes.scan_dependencies", return_value=[])
    @patch("prism_reviewer.agents.nodes.find_text", return_value=[])
    @patch("os.path.isfile", return_value=True)
    @patch("prism_reviewer.agents.nodes.ResilientLLMClient.completion_with_retry")
    def test_graph_execution_multi_region(
        self,
        mock_completion,
        mock_isfile,
        mock_find_text,
        mock_scan_deps,
        mock_ast_analyzer_class,
        mock_get_repo_structure,
    ) -> None:
        """The compiled graph correctly partitions a larger diff into multiple regions and runs the agents on each region."""
        mock_analyzer = MagicMock()
        mock_analyzer.get_ast_skeleton.return_value = {"symbols": []}
        mock_ast_analyzer_class.return_value = mock_analyzer

        large_diff = (
            "diff --git a/foo.py b/foo.py\n"
            "@@ -1,1 +1,2 @@\n"
            " context_foo\n"
            "+new_foo\n"
            "diff --git a/bar.py b/bar.py\n"
            "@@ -1,1 +1,2 @@\n"
            " context_bar\n"
            "+new_bar\n"
        )

        with patch("prism_reviewer.agents.nodes.config") as mock_config:
            mock_config.get.return_value = {"max_region_lines": 2}
            
            # 2 regions * 3 agents = 6 LLM calls
            mock_completion.side_effect = [
                _mock_agent_response("warden"),
                _mock_agent_response("architect"),
                _mock_agent_response("inspector"),
                _mock_agent_response("warden"),
                _mock_agent_response("architect"),
                _mock_agent_response("inspector"),
            ]

            state = _make_state()
            state["git_diff"] = large_diff
            graph = build_graph()

            final_state = graph.invoke(state)

        assert len(final_state["raw_findings"]) == 6
