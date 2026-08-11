"""Tests for the verifier_node (hallucination guard + dedup filter)."""

import pytest

from prism_reviewer.agents.state import Finding, ReviewState
from prism_reviewer.agents.verifier import verifier_node


# Minimal diff that puts "foo.py" line 2 and line 3 in the valid set
SAMPLE_DIFF = (
    "diff --git a/foo.py b/foo.py\n"
    "@@ -1,3 +1,4 @@\n"
    " context_line_1\n"   # line 1 (context)
    "+added_line\n"       # line 2 (added)
    " context_line_3\n"   # line 3 (context)
    " context_line_4\n"   # line 4 (context)
)


def _make_finding(
    file: str = "foo.py",
    line: int = 2,
    agent: str = "warden",
    signature: str = "sig123",
) -> Finding:
    return Finding(
        file=file,
        line=line,
        severity="ADVISORY",
        agent=agent,
        message="Test finding",
        signature=signature,
    )


def _make_state(
    raw_findings: list[Finding],
    previous_signatures: list[str] | None = None,
    git_diff: str = SAMPLE_DIFF,
) -> ReviewState:
    return ReviewState(
        repo_path="/tmp/repo",
        git_diff=git_diff,
        pr_title="Test PR",
        pr_description="",
        repo_structure="",
        ast_map={},
        codelens_dep_summary="",
        codelens_search_hits="",
        context_content="",
        rules_content="",
        previous_signatures=previous_signatures or [],
        regions=[],
        raw_findings=raw_findings,
        verified_findings=[],
        report_markdown="",
    )


class TestVerifierNode:
    def test_valid_finding_passes_through(self) -> None:
        """A finding on a line that exists in the diff should pass through."""
        finding = _make_finding(file="foo.py", line=2, signature="unique-sig")
        state = _make_state(raw_findings=[finding])
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 1

    def test_hallucinated_line_is_dropped(self) -> None:
        """A finding on line 99 (not in the diff) must be dropped."""
        finding = _make_finding(file="foo.py", line=99, signature="unique-sig")
        state = _make_state(raw_findings=[finding])
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 0

    def test_hallucinated_file_is_dropped(self) -> None:
        """A finding on a completely different file (not in the diff) must be dropped."""
        finding = _make_finding(file="nonexistent.py", line=2, signature="unique-sig")
        state = _make_state(raw_findings=[finding])
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 0

    def test_duplicate_signature_is_dropped(self) -> None:
        """A finding whose signature appears in previous_signatures must be dropped."""
        finding = _make_finding(file="foo.py", line=2, signature="known-sig")
        state = _make_state(
            raw_findings=[finding],
            previous_signatures=["known-sig"],
        )
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 0

    def test_new_signature_passes_through(self) -> None:
        """A finding whose signature is NOT in previous_signatures must pass through."""
        finding = _make_finding(file="foo.py", line=2, signature="brand-new-sig")
        state = _make_state(
            raw_findings=[finding],
            previous_signatures=["some-other-sig"],
        )
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 1

    def test_mixed_findings_filtered_correctly(self) -> None:
        """Combination of valid, hallucinated, and duplicate findings."""
        valid = _make_finding(file="foo.py", line=2, signature="valid-sig")
        hallucinated = _make_finding(file="foo.py", line=99, signature="halluc-sig")
        duplicate = _make_finding(file="foo.py", line=3, signature="dup-sig")

        state = _make_state(
            raw_findings=[valid, hallucinated, duplicate],
            previous_signatures=["dup-sig"],
        )
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 1
        assert result["verified_findings"][0]["signature"] == "valid-sig"

    def test_empty_raw_findings_returns_empty_verified(self) -> None:
        """An empty raw_findings list should produce an empty verified_findings list."""
        state = _make_state(raw_findings=[])
        result = verifier_node(state)
        assert result["verified_findings"] == []

    def test_empty_diff_drops_all_findings(self) -> None:
        """With an empty diff, all findings should be dropped (no valid lines)."""
        finding = _make_finding(file="foo.py", line=2, signature="sig")
        state = _make_state(raw_findings=[finding], git_diff="")
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 0

    def test_context_lines_are_valid(self) -> None:
        """Context lines (unchanged, shown in diff) should be accepted."""
        # Line 1 is a context line in SAMPLE_DIFF
        finding = _make_finding(file="foo.py", line=1, signature="ctx-sig")
        state = _make_state(raw_findings=[finding])
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 1

    def test_return_dict_has_verified_findings_key(self) -> None:
        """verifier_node must always return a dict with 'verified_findings'."""
        state = _make_state(raw_findings=[])
        result = verifier_node(state)
        assert "verified_findings" in result

    def test_intra_run_duplicate_signatures_are_dropped(self) -> None:
        """Duplicate findings with the same signature in raw_findings of a single run must be dropped."""
        finding1 = _make_finding(file="foo.py", line=2, agent="warden", signature="shared-sig")
        finding2 = _make_finding(file="foo.py", line=2, agent="inspector", signature="shared-sig")
        state = _make_state(raw_findings=[finding1, finding2])
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 1

    def test_intra_run_duplicate_location_and_message_are_dropped(self) -> None:
        """Duplicate findings on the same file, line, agent, and message within a single run must be dropped."""
        finding1 = _make_finding(file="foo.py", line=2, agent="warden", signature="sig1")
        finding2 = _make_finding(file="foo.py", line=2, agent="warden", signature="sig2")
        state = _make_state(raw_findings=[finding1, finding2])
        result = verifier_node(state)
        assert len(result["verified_findings"]) == 1

