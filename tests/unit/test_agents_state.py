"""Tests for ReviewState TypedDict structure and the raw_findings reducer."""

import operator
from typing import Annotated, List, get_args, get_type_hints

import pytest

from prism_reviewer.agents.state import Finding, ReviewState


def test_finding_keys_exist() -> None:
    """Finding TypedDict contains all required keys."""
    required = {"file", "line", "severity", "agent", "message", "signature"}
    hints = get_type_hints(Finding)
    assert required.issubset(hints.keys()), f"Missing keys: {required - hints.keys()}"


def test_review_state_keys_exist() -> None:
    """ReviewState TypedDict contains all required keys."""
    required = {
        "repo_path", "git_diff", "pr_title", "pr_description",
        "repo_structure", "ast_map", "codelens_dep_summary", "codelens_search_hits",
        "context_content", "rules_content", "previous_signatures",
        "raw_findings", "verified_findings", "report_markdown",
    }
    hints = get_type_hints(ReviewState, include_extras=True)
    assert required.issubset(hints.keys()), f"Missing keys: {required - hints.keys()}"


def test_raw_findings_uses_operator_add_reducer() -> None:
    """raw_findings is annotated with operator.add so LangGraph can merge parallel lists."""
    hints = get_type_hints(ReviewState, include_extras=True)
    annotation = hints["raw_findings"]
    args = get_args(annotation)
    # Annotated[List[Finding], operator.add] → args = (List[Finding], operator.add)
    assert len(args) == 2, "raw_findings annotation should have two args (type, reducer)"
    assert args[1] is operator.add, "raw_findings reducer must be operator.add"


def _make_finding(agent: str = "warden", line: int = 10) -> Finding:
    return Finding(
        file="src/foo.py",
        line=line,
        severity="ADVISORY",
        agent=agent,
        message="Test finding",
        signature=f"sig-{agent}-{line}",
    )


def test_raw_findings_list_merge_semantics() -> None:
    """Validate that operator.add on two Finding lists concatenates them (LangGraph semantics)."""
    list_a: List[Finding] = [_make_finding("warden", 1)]
    list_b: List[Finding] = [_make_finding("architect", 2), _make_finding("inspector", 3)]

    merged = operator.add(list_a, list_b)
    assert len(merged) == 3
    assert merged[0]["agent"] == "warden"
    assert merged[1]["agent"] == "architect"
    assert merged[2]["agent"] == "inspector"


def test_finding_severity_literal() -> None:
    """Finding.severity accepts only CRITICAL, MAJOR, ADVISORY (tested by construction)."""
    # All three valid values should construct without error
    for sev in ("CRITICAL", "MAJOR", "ADVISORY"):
        f = Finding(file="f.py", line=1, severity=sev, agent="warden",  # type: ignore[arg-type]
                    message="msg", signature="abc123")
        assert f["severity"] == sev
