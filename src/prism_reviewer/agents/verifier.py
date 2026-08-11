"""
prism_reviewer.agents.verifier
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Verifier node for the PrismReviewer LangGraph pipeline.

Responsibilities
----------------
1. **Hallucination guard**: drops any finding whose ``(file, line)`` pair does
   not exist in the raw diff.  This prevents the agents from commenting on
   lines they invented.
2. **Idempotent deduplication**: drops any finding whose ``signature`` matches
   a signature from the previous run, preventing the same issue from being
   reported repeatedly on unchanged code.

The node is intentionally simple — it performs only mechanical filtering, no
inference.  Accordingly, it uses ``reasoning_effort=low`` when an LLM call is
ever needed (currently it performs no LLM calls at all).
"""

from typing import Any, Dict, List

from ..core.logger import get_logger
from ..utils.git_utils import normalize_file_path, parse_diff_changed_lines
from .nodes import NodeLogger
from .state import Finding, ReviewState

logger = get_logger("prism_reviewer.agents.verifier")


def verifier_node(state: ReviewState) -> Dict[str, Any]:
    """
    Verifier node — hallucination guard and idempotent deduplication.

    Takes ``raw_findings`` (the merged output of all three parallel agents)
    and filters it down to ``verified_findings`` by:

    1. Dropping findings whose ``(file, line)`` pair is not in the diff.
    2. Dropping findings whose ``signature`` matches a previous-run signature.

    Args:
        state: The current ``ReviewState`` dict.  Key fields consumed:
               - ``raw_findings``       — merged output of all three agents.
               - ``git_diff``           — raw unified diff for line validation.
               - ``previous_signatures``— list of signatures from the last run.

    Returns:
        Partial state update: ``{"verified_findings": [...]}``.
    """
    node_log = NodeLogger(logger, "VERIFIER Node")

    raw_findings: List[Finding] = state.get("raw_findings", [])

    # Count per-agent for the log
    agent_counts: Dict[str, int] = {"warden": 0, "architect": 0, "inspector": 0}
    for f in raw_findings:
        agent = f.get("agent", "unknown")
        agent_counts[agent] = agent_counts.get(agent, 0) + 1

    node_log.record(
        f"Raw findings received: {len(raw_findings)} "
        f"(warden={agent_counts.get('warden', 0)}, "
        f"architect={agent_counts.get('architect', 0)}, "
        f"inspector={agent_counts.get('inspector', 0)})"
    )

    # Build the set of valid (file, line) pairs from the diff
    valid_lines = parse_diff_changed_lines(state.get("git_diff", ""))

    # Convert previous_signatures list to a set for O(1) lookup
    previous_sigs: set[str] = set(state.get("previous_signatures", []))

    verified: List[Finding] = []
    dropped_hallucination = 0
    dropped_duplicate = 0

    for finding in raw_findings:
        file_path: str = normalize_file_path(finding.get("file", ""))
        line_num: int = finding.get("line", 0)
        signature: str = finding.get("signature", "")

        # Guard 1: line must exist in the diff
        if (file_path, line_num) not in valid_lines:
            dropped_hallucination += 1
            continue

        # Update normalized path in finding object
        finding["file"] = file_path

        # Guard 2: signature must not match a previous run
        if signature and signature in previous_sigs:
            dropped_duplicate += 1
            continue

        verified.append(finding)

    node_log.record(f"Dropped {dropped_hallucination}: line numbers not present in diff")
    node_log.record(f"Dropped {dropped_duplicate}: duplicate signature match")
    node_log.record(f"Verified findings: {len(verified)}")
    node_log.flush()

    return {"verified_findings": verified}
