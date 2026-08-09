"""
Tests for aggregator_node and the _render_markdown helper.

Note on severity in test fixtures
----------------------------------
The aggregator is the one node whose correctness *requires* testing all three
severity values — the sort-order logic is meaningless without CRITICAL, MAJOR,
and ADVISORY present in the input.  These findings are constructed directly and
are never passed to a mock LLM or through the real reporting pipeline.
"""

import pytest

from prism_reviewer.agents.aggregator import _render_markdown, aggregator_node
from prism_reviewer.agents.state import Finding, ReviewState


def _make_finding(
    file: str = "foo.py",
    line: int = 1,
    severity: str = "ADVISORY",
    agent: str = "warden",
) -> Finding:
    return Finding(
        file=file,
        line=line,
        severity=severity,  # type: ignore[arg-type]
        agent=agent,
        message=f"{severity} finding at {file}:{line}",
        signature=f"sig-{severity}-{file}-{line}",
    )


def _make_state(verified_findings: list[Finding], pr_title: str = "Test PR") -> ReviewState:
    return ReviewState(
        repo_path="/tmp/repo",
        git_diff="",
        pr_title=pr_title,
        pr_description="",
        repo_structure="",
        ast_map={},
        codelens_dep_summary="",
        codelens_search_hits="",
        context_content="",
        rules_content="",
        previous_signatures=[],
        regions=[],
        raw_findings=[],
        verified_findings=verified_findings,
        report_markdown="",
    )


class TestAggregatorNode:
    def test_returns_report_markdown_key(self) -> None:
        """aggregator_node must return a dict with 'report_markdown'."""
        state = _make_state([])
        result = aggregator_node(state)
        assert "report_markdown" in result

    def test_empty_findings_produces_no_findings_message(self) -> None:
        """An empty verified_findings list should produce a 'no findings' message."""
        state = _make_state([])
        result = aggregator_node(state)
        assert "No findings" in result["report_markdown"] or "no findings" in result["report_markdown"].lower()

    def test_report_contains_pr_title(self) -> None:
        """The rendered report must include the PR title."""
        state = _make_state([], pr_title="My special PR")
        result = aggregator_node(state)
        assert "My special PR" in result["report_markdown"]

    def test_sort_order_critical_before_major_before_advisory(self) -> None:
        """Findings must appear in CRITICAL → MAJOR → ADVISORY order."""
        findings = [
            _make_finding(severity="ADVISORY", file="a.py", line=1),
            _make_finding(severity="CRITICAL", file="b.py", line=1),
            _make_finding(severity="MAJOR",    file="c.py", line=1),
        ]
        state = _make_state(findings)
        result = aggregator_node(state)
        report = result["report_markdown"]

        critical_pos = report.index("CRITICAL")
        major_pos    = report.index("MAJOR")
        advisory_pos = report.index("ADVISORY")
        assert critical_pos < major_pos < advisory_pos, (
            "Report must list CRITICAL before MAJOR before ADVISORY"
        )

    def test_within_tier_sort_by_file_then_line(self) -> None:
        """Within the same severity tier, findings must sort by file then line."""
        findings = [
            _make_finding(severity="ADVISORY", file="z.py", line=10),
            _make_finding(severity="ADVISORY", file="a.py", line=50),
            _make_finding(severity="ADVISORY", file="a.py", line=5),
        ]
        state = _make_state(findings)
        result = aggregator_node(state)

        # Extract the order from the Markdown table rows
        lines = result["report_markdown"].splitlines()
        table_rows = [l for l in lines if "| `" in l]

        # Expected: a.py:5 → a.py:50 → z.py:10
        assert "a.py" in table_rows[0]
        assert "5" in table_rows[0]
        assert "a.py" in table_rows[1]
        assert "50" in table_rows[1]
        assert "z.py" in table_rows[2]

    def test_report_contains_severity_section_headers(self) -> None:
        """The rendered report must include section headers for present severities."""
        findings = [
            _make_finding(severity="CRITICAL"),
            _make_finding(severity="ADVISORY"),
        ]
        state = _make_state(findings)
        result = aggregator_node(state)
        report = result["report_markdown"]
        assert "CRITICAL" in report
        assert "ADVISORY" in report
        # MAJOR section should NOT appear since no MAJOR findings
        # (It appears in the header count line; check the section header specifically)
        assert "## " + "⚠️ MAJOR" not in report

    def test_report_contains_table_rows_for_findings(self) -> None:
        """Every finding must produce a table row in the Markdown report."""
        findings = [
            _make_finding(severity="ADVISORY", file="foo.py", line=42),
        ]
        state = _make_state(findings)
        result = aggregator_node(state)
        assert "foo.py" in result["report_markdown"]
        assert "42" in result["report_markdown"]


class TestRenderMarkdown:
    def test_no_findings_no_table(self) -> None:
        """_render_markdown with empty findings must not emit a table."""
        report = _render_markdown("Test PR", [], {"CRITICAL": 0, "MAJOR": 0, "ADVISORY": 0})
        assert "|" not in report or "Agent" not in report  # no table headers

    def test_finding_message_appears_in_report(self) -> None:
        """The finding message must appear verbatim in the rendered table."""
        f = _make_finding(severity="ADVISORY")
        report = _render_markdown("PR", [f], {"CRITICAL": 0, "MAJOR": 0, "ADVISORY": 1})
        assert f["message"] in report

    def test_report_has_preamble_header(self) -> None:
        """Report must contain the Prism Reviewer AI header."""
        report = _render_markdown("PR", [], {"CRITICAL": 0, "MAJOR": 0, "ADVISORY": 0})
        assert "Prism Reviewer AI" in report

    def test_report_includes_pr_id_when_provided(self) -> None:
        """Report header must include '#PR_ID - PR_TITLE' when pr_id is provided."""
        report = _render_markdown("Plugin SPIFFE outbound auth", [], {"CRITICAL": 0, "MAJOR": 0, "ADVISORY": 0}, pr_id=1139)
        assert "#1139 - Plugin SPIFFE outbound auth" in report

    def test_report_includes_version_footer(self) -> None:
        """Report footer must include the Prism Reviewer AI version note."""
        from prism_reviewer import __version__
        report = _render_markdown("PR", [], {"CRITICAL": 0, "MAJOR": 0, "ADVISORY": 0})
        assert f"Generated by Prism Reviewer AI v{__version__}" in report


