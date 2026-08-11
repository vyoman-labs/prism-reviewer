"""
prism_reviewer.agents.aggregator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Aggregator node for the PrismReviewer LangGraph pipeline.

Responsibilities
----------------
1. Sorts ``verified_findings`` by severity tier (CRITICAL → MAJOR → ADVISORY),
   then by filename, then by line number within each tier.
2. Renders a structured Markdown report with per-severity sections, per-finding
   table rows, and a summary footer.
3. Returns the ``report_markdown`` string for writing to disk or posting to GitHub.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import __version__
from ..core.logger import get_logger
from .nodes import NodeLogger
from .state import Finding, ReviewState

logger = get_logger("prism_reviewer.agents.aggregator")


# Severity sort order: lower index = higher priority
_SEVERITY_ORDER: Dict[str, int] = {"CRITICAL": 0, "MAJOR": 1, "ADVISORY": 2}

# Emoji badges for each severity tier
_SEVERITY_EMOJI: Dict[str, str] = {
    "CRITICAL": "\U0001f6a8",  # 🚨
    "MAJOR": "\u26a0\ufe0f",   # ⚠️
    "ADVISORY": "\U0001f4a1",  # 💡
}

# Emoji badges for each agent
_AGENT_EMOJI: Dict[str, str] = {
    "warden": "\U0001f46e",    # 👮
    "architect": "\U0001f4d0", # 📐
    "inspector": "\U0001f50d", # 🔍
}


def aggregator_node(state: ReviewState) -> Dict[str, Any]:
    """
    Aggregator node — sorts findings and renders the Markdown review report.

    Args:
        state: The current ``ReviewState`` dict.  Key fields consumed:
               - ``verified_findings``  — filtered findings from ``verifier_node``.
               - ``pr_title``           — pull request title for the report header.
               - ``resolved_signatures`` — optional list of signatures for findings
                 whose GitHub inline comment threads have been resolved by a reviewer.

    Returns:
        Partial state update: ``{"report_markdown": "..."}``.
    """
    node_log = NodeLogger(logger, "AGGREGATOR Node")

    findings: List[Finding] = state.get("verified_findings", [])
    pr_title: str = state.get("pr_title", "") or "(untitled)"
    pr_id: Any = state.get("pr_id")
    resolved_sigs: set[str] = set(state.get("resolved_signatures", []))

    # Partition findings into active vs. resolved-by-reviewer
    active_findings: List[Finding] = []
    resolved_findings: List[Finding] = []
    for f in findings:
        sig = f.get("signature", "")
        if sig and sig in resolved_sigs:
            resolved_findings.append(f)
        else:
            active_findings.append(f)

    # Count per severity tier for the log (active only)
    counts: Dict[str, int] = {"CRITICAL": 0, "MAJOR": 0, "ADVISORY": 0}
    for f in active_findings:
        sev = f.get("severity", "ADVISORY")
        if sev in counts:
            counts[sev] += 1

    node_log.record(
        f"📊 Findings tally: 🚨 {counts['CRITICAL']} CRITICAL, "
        f"⚠️ {counts['MAJOR']} MAJOR, 💡 {counts['ADVISORY']} ADVISORY"
    )
    if resolved_findings:
        node_log.record(f"✅ {len(resolved_findings)} finding(s) marked as resolved by reviewer")

    # Sort active findings: severity tier → file → line
    sorted_findings = sorted(
        active_findings,
        key=lambda f: (
            _SEVERITY_ORDER.get(f.get("severity", "ADVISORY"), 2),
            f.get("file", ""),
            f.get("line", 0),
        ),
    )

    report = _render_markdown(
        pr_title, sorted_findings, counts, pr_id=pr_id, resolved_findings=resolved_findings
    )
    node_log.record(f"📝 Report generated: {len(report)} chars")
    node_log.flush()

    return {"report_markdown": report}


# Hidden marker embedded in every summary comment body.  Used by the GitHub
# publishing layer to locate and update the existing summary comment in-place.
SUMMARY_COMMENT_MARKER: str = "<!-- prism-reviewer-summary -->"


def _render_markdown(
    pr_title: str,
    findings: List[Finding],
    counts: Dict[str, int],
    pr_id: Any = None,
    resolved_findings: Optional[List[Finding]] = None,
) -> str:
    """
    Renders the final review report as a Markdown string.

    Args:
        pr_title: Pull request title for the report header.
        findings: Sorted list of active (unresolved) verified findings.
        counts:   Pre-computed dict of ``{severity: count}`` for *active* findings.
        pr_id:    Optional pull request ID or number.
        resolved_findings: Optional list of findings whose GitHub inline comment
            threads have been manually resolved by a reviewer.  When provided,
            these are shown in a collapsible ``✅ Resolved`` section.

    Returns:
        Full Markdown report as a string, including a hidden
        ``<!-- prism-reviewer-summary -->`` marker for sticky-comment detection.
    """
    if resolved_findings is None:
        resolved_findings = []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = sum(counts.values())

    pr_header = f"#{pr_id} - {pr_title}" if pr_id is not None and str(pr_id).strip() else pr_title

    # The hidden marker MUST appear first so the search/update logic can find it
    # even when the comment is truncated in API list responses.
    lines: List[str] = [
        SUMMARY_COMMENT_MARKER,
        "# \U0001f50d Prism Reviewer AI Code Review Report",
        "",
        f"**Pull Request:** {pr_header}",
        f"**Reviewed:** {now}",
        "**Agent Council:** \U0001f46e Warden \u00b7 \U0001f4d0 Architect \u00b7 \U0001f50d Inspector",
        f"**Findings:** {total} total "
        f"(\U0001f6a8 {counts['CRITICAL']} critical "
        f"\u00b7 \u26a0\ufe0f {counts['MAJOR']} major "
        f"\u00b7 \U0001f4a1 {counts['ADVISORY']} advisory)",
        "",
    ]

    if not findings:
        lines.append(
            "*No findings identified. The diff looks clean across all review lenses.*"
        )
    else:
        # Emit one section per severity tier, skipping empty tiers
        for severity in ("CRITICAL", "MAJOR", "ADVISORY"):
            tier_findings = [f for f in findings if f.get("severity") == severity]
            if not tier_findings:
                continue

            emoji = _SEVERITY_EMOJI[severity]
            lines += [
                f"## {emoji} {severity}",
                "",
                "| Agent | File | Line | Message |",
                "| --- | --- | --- | --- |",
            ]
            for f in tier_findings:
                agent = f.get("agent", "unknown")
                agent_badge = _AGENT_EMOJI.get(agent, "\U0001f916")  # 🤖 fallback
                lines.append(
                    f"| {agent_badge} {agent} "
                    f"| `{f.get('file', '?')}` "
                    f"| {f.get('line', '?')} "
                    f"| {f.get('message', '?')} |"
                )
            lines.append("")

    # ── Resolved findings section ────────────────────────────────────────────
    if resolved_findings:
        lines += [
            "<details>",
            "<summary>✅ Resolved findings</summary>",
            "",
            "The following findings were raised in a previous review cycle and have "
            "since been resolved (either fixed in code or manually resolved on GitHub).",
            "",
            "| Agent | File | Line | Message |",
            "| --- | --- | --- | --- |",
        ]
        for f in resolved_findings:
            agent = f.get("agent", "unknown")
            agent_badge = _AGENT_EMOJI.get(agent, "\U0001f916")  # 🤖 fallback
            lines.append(
                f"| {agent_badge} {agent} "
                f"| `{f.get('file', '?')}` "
                f"| {f.get('line', '?')} "
                f"| ~~{f.get('message', '?')}~~ |"
            )
        lines += ["", "</details>", ""]

    lines += ["---", f"*Generated by Prism Reviewer AI v{__version__}*"]

    return "\n".join(lines)
