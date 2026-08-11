"""
prism_reviewer.agents.nodes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
LangGraph node functions and supporting helpers for the PrismReviewer agent
pipeline.

Design principles applied here:
- Every node is a plain ``def`` function — no classes, no decorators, no magic.
- Each node has a single responsibility: receive state, produce a partial update.
- Prompt assembly is separated from the LLM call, which is separated from JSON
  parsing.  Each step is independently testable.
- ``NodeLogger`` buffers per-node log entries and flushes them as one atomic
  block, eliminating interleaved output from parallel agent threads.

Public nodes
------------
build_context_node  Gathers AST, dep-scan, and search context before fan-out.
warden_node         Security & compliance review agent.
architect_node      Architecture & performance review agent.
inspector_node      Clean code & logic review agent.

Internal helpers
----------------
NodeLogger          Buffered logger that flushes as one atomic block.
_build_user_turn    Assembles the structured, labeled user-turn message.
_parse_findings     Parses and stamps LLM JSON output into Finding dicts.
_extract_touched_files  Extracts changed file paths from a unified diff string.
_serialize_ast_map  Formats the AST skeleton map for prompt injection.
_serialize_dep_scan Formats dependency-scan results for prompt injection.
"""

import json
import os
import re
import time
from typing import Any, Dict, List

from ..core.config import Config, GlobalConfig, config
from ..core.logger import get_logger
from ..codelens.dependency_scanner import scan_dependencies
from ..codelens.parser import UniversalASTAnalyzer
from ..codelens.searcher import find_text
from ..services.llm import ResilientLLMClient
from ..utils.git_utils import (
    group_diffs_into_regions,
    run_git_command,
    split_diff_by_file,
)
from ..utils.signature import get_finding_signature
from .prompts import (
    ARCHITECT_SYSTEM_PROMPT,
    INSPECTOR_SYSTEM_PROMPT,
    OUTPUT_SCHEMA_BLOCK,
    WARDEN_SYSTEM_PROMPT,
)
from .state import Finding, ReviewState


# ---------------------------------------------------------------------------
# NodeLogger — buffered, atomic log flusher
# ---------------------------------------------------------------------------

class NodeLogger:
    """
    Buffers log entries during a node's execution and flushes them as a single
    atomic ``logger.info()`` call on completion.

    Because ``flush()`` is one logging call, Python's logging lock guarantees
    the entire block is written without interleaving from parallel agent threads.
    The footer line carries the total wall-clock elapsed time for the node.

    Usage::

        node_log = NodeLogger(logger, "WARDEN Node")
        node_log.record("Dispatching to LLM...")
        node_log.record("Parsed 4 findings")
        node_log.flush()  # emits the whole block atomically
    """

    def __init__(self, logger: Any, label: str) -> None:
        """
        Args:
            logger: A ``logging.Logger`` instance to flush to.
            label:  Human-readable label shown in the block header (e.g. ``"WARDEN Node"``).
        """
        self._logger = logger
        self._label = label
        self._start = time.monotonic()
        self._lines: List[str] = []

    def record(self, message: str) -> None:
        """
        Records a log entry with elapsed time relative to node start.

        Args:
            message: The log message to buffer.
        """
        elapsed = time.monotonic() - self._start
        self._lines.append(f"  +{elapsed:.2f}s  {message}")

    def flush(self) -> None:
        """
        Emits the entire buffered log as one atomic block to the real logger.

        The footer line shows the total elapsed time for the node so it is
        easy to spot the slowest agent in parallel execution output.
        """
        total_elapsed = time.monotonic() - self._start
        sep = "\u2500" * 52
        header = f"\u2500\u2500 {self._label} \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500"
        footer = f"\u2500\u2500 Total: {total_elapsed:.2f}s {'\u2500' * 20}"
        block = "\n".join([header] + self._lines + [footer])
        self._logger.info("\n" + block)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _count_tokens(text: str, model_name: str | None = None) -> int:
    """
    Estimates token count for a string using LiteLLM's token_counter,
    falling back to character heuristic (len(text) // 4) if unavailable.
    """
    if not text:
        return 0
    try:
        import litellm
        model = model_name or Config.llm_model_name() or "gpt-4o"
        return litellm.token_counter(model=model, text=text)
    except Exception:
        return max(1, len(text) // 4)


def _extract_touched_files(git_diff: str) -> List[str]:
    """
    Extracts the list of changed file paths from a unified diff string.

    Parses ``diff --git a/... b/...`` header lines and returns the ``b/`` path
    (the new file name) for each changed file.

    Args:
        git_diff: Raw unified diff string.

    Returns:
        List of relative file paths touched by the diff.
    """
    pattern = re.compile(r"^diff --git a/.+ b/(.+)$", re.MULTILINE)
    return pattern.findall(git_diff)


def _serialize_ast_map(ast_map: Dict[str, Any]) -> str:
    """
    Formats the AST skeleton map into a human-readable string for prompt injection.

    Args:
        ast_map: Mapping of file path → ``UniversalASTAnalyzer.get_ast_skeleton()`` dict.

    Returns:
        A multi-line string with one section per file listing its symbols.
    """
    if not ast_map:
        return "(no AST data available)"

    sections: List[str] = []
    for file_path, skeleton in ast_map.items():
        symbols = skeleton.get("symbols", [])
        if not symbols:
            continue
        sym_lines = [
            f"  - {sym.get('type', 'unknown')} `{sym.get('name', '<anonymous>')}` "
            f"(lines {sym.get('start_line', '?')}–{sym.get('end_line', '?')})"
            for sym in symbols
        ]
        sections.append(f"**{file_path}**\n" + "\n".join(sym_lines))

    return "\n\n".join(sections) if sections else "(no symbols extracted)"


def _serialize_dep_scan(scan_results: List[Any]) -> str:
    """
    Formats dependency-scan results into a prompt-friendly string.

    Args:
        scan_results: List of result dicts from ``scan_dependencies()``.

    Returns:
        A multi-line string summarising manifests, dependency counts, and warnings.
    """
    if not scan_results:
        return "(no manifest files found)"

    parts: List[str] = []
    for result in scan_results:
        file_name = result.get("file", "unknown")
        deps = result.get("dependencies", [])
        issues = result.get("issues", [])
        parts.append(f"**{file_name}**: {len(deps)} dependencies, {len(issues)} warnings")
        for issue in issues:
            parts.append(f"  \u26a0 {issue.get('message', '')}")

    return "\n".join(parts)


def _get_repo_structure(repo_path: str) -> str:
    """
    Returns a flat list of files tracked by git, capped at 100 entries.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        Newline-separated list of tracked file paths, or a fallback message.
    """
    try:
        output = run_git_command(repo_path, ["ls-files"])
        files = [f.strip() for f in output.splitlines() if f.strip()]
        return "\n".join(files[:100])
    except Exception:
        return "(could not retrieve repository structure)"


def _load_readme_content(repo_path: str) -> str:
    """
    Reads the repository root ``README.md`` file, truncating it at the last complete
    line boundary if its length exceeds ``max_readme_chars`` (default 10000).

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        The (possibly truncated) README content string, or "(none)" if not found or unreadable.
    """
    max_chars_cfg = config.get("agents", {}).get("max_readme_chars", 10000)
    try:
        max_chars = int(max_chars_cfg)
    except (ValueError, TypeError):
        max_chars = 10000

    readme_path = os.path.join(repo_path, "README.md")
    if not os.path.isfile(readme_path):
        return "(none)"

    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return "(none)"

    if not content.strip():
        return "(none)"

    if len(content) <= max_chars:
        return content

    # Truncate at the last complete line boundary within max_chars
    truncated_raw = content[:max_chars]
    last_newline = truncated_raw.rfind("\n")
    if last_newline != -1:
        truncated = truncated_raw[:last_newline]
    else:
        truncated = truncated_raw

    return f"{truncated}\n\n... [README truncated to max {max_chars} characters]"


def _build_user_turn(state: ReviewState, agent_name: str) -> str:
    """
    Assembles the structured, labeled user-turn message for an agent node.

    Optimized for LLM Prompt Caching:
    Injects static, repository-wide shared context first (Repo Structure,
    Codelens AST/Search/Dep Data, README, Context, Rules) to maximize prompt cache
    hits across parallel agent nodes and diff regions.  Dynamic PR metadata, git diff,
    and output schema are appended at the end.

    Args:
        state:      The current ``ReviewState`` dict.
        agent_name: Name of the agent (used only for future extensibility).

    Returns:
        A fully assembled multi-section prompt string.
    """
    ast_text = _serialize_ast_map(state.get("ast_map", {}))

    current_region = state.get("current_region")
    if current_region:
        region_idx = current_region.get("region_index", 1)
        total_regions = current_region.get("total_regions", 1)
        files_list = ", ".join(current_region.get("files", []))
        git_diff_header = f"## Git Diff (Region {region_idx} of {total_regions} - Files: {files_list})"
    else:
        git_diff_header = "## Git Diff"

    parts = [
        # --- Static Shared Prefix (Cacheable across all nodes & regions) ---
        "## Repository Structure",
        state.get("repo_structure") or "(not available)",
        "",
        "## Dependency Analysis (Codelens: dep-scan)",
        state.get("codelens_dep_summary") or "(no manifests found)",
        "",
        "## Code Search Hits (Codelens: searcher)",
        state.get("codelens_search_hits") or "(no cross-reference hits found)",
        "",
        "## Code Symbol Map (Codelens: AST)",
        ast_text,
        "",
        "## Repository README",
        state.get("readme_content") or "(none)",
        "",
        "## Project Context",
        state.get("context_content") or "(none)",
        "",
        "## Review Rules",
        state.get("rules_content") or "(none)",
        "",
        # --- Dynamic Suffix (PR-specific / Region-specific) ---
        "## Pull Request Context",
        f"Title: {state.get('pr_title') or '(no title)'}",
        f"Description:\n{state.get('pr_description') or '(no description provided)'}",
        "",
        git_diff_header,
        state.get("git_diff") or "(empty diff)",
        "",
        OUTPUT_SCHEMA_BLOCK,
    ]
    return "\n".join(parts)


def _parse_findings(
    raw_response: str,
    agent_name: str,
    repo_path: str,
    node_log: NodeLogger,
) -> List[Finding]:
    """
    Parses the LLM JSON response and stamps each finding with the agent name
    and a content-hash signature.

    Returns an empty list (with a warning recorded) on any parse error so the
    node always returns a valid state update even when the model misbehaves.

    Args:
        raw_response: Raw string returned by ``ResilientLLMClient.completion_with_retry()``.
        agent_name:   Name of the calling agent (``"warden"`` / ``"architect"`` / ``"inspector"``).
        repo_path:    Absolute path to the repository root (for signature computation).
        node_log:     The ``NodeLogger`` for the current node (to record warnings).

    Returns:
        List of ``Finding`` dicts, each stamped with ``agent`` and ``signature``.
    """
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        node_log.record(f"WARNING: JSON parse failed — {exc}. Returning empty findings.")
        return []

    raw_list = data.get("findings", [])
    if not isinstance(raw_list, list):
        node_log.record("WARNING: 'findings' is not a list. Returning empty findings.")
        return []

    findings: List[Finding] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue

        file_val: str = str(item.get("file", ""))
        line_val: int = 1
        try:
            line_val = int(item.get("line", 1))
        except (ValueError, TypeError):
            pass

        severity_raw = str(item.get("severity", "ADVISORY")).upper()
        severity: Any = severity_raw if severity_raw in ("CRITICAL", "MAJOR", "ADVISORY") else "ADVISORY"

        message: str = str(item.get("message", ""))

        signature = get_finding_signature(repo_path, file_val, line_val, agent_name)

        findings.append(
            Finding(
                file=file_val,
                line=line_val,
                severity=severity,
                agent=agent_name,
                message=message,
                signature=signature,
            )
        )

    return findings


# ---------------------------------------------------------------------------
# Context builder node
# ---------------------------------------------------------------------------

def build_context_node(state: ReviewState) -> Dict[str, Any]:
    """
    Gathers all repository context before the agent fan-out.

    Runs once at graph start.  Populates ``repo_structure``, ``ast_map``,
    ``codelens_dep_summary``, and ``codelens_search_hits`` in the state so that
    all three parallel agent nodes receive the same fully-assembled context
    without redundant I/O.

    Args:
        state: The current ``ReviewState`` dict.

    Returns:
        Partial state update dict with the four context fields populated.
    """
    logger = get_logger("prism_reviewer.agents.build_context")
    node_log = NodeLogger(logger, "BUILD_CONTEXT Node")

    repo_path: str = state["repo_path"]
    git_diff: str = state.get("git_diff", "")

    # 1. Flat repo file list
    repo_structure = _get_repo_structure(repo_path)
    node_log.record(f"Repo structure: {len(repo_structure.splitlines())} tracked files")

    # 2. Extract files touched by this diff
    touched_files = _extract_touched_files(git_diff)
    node_log.record(f"Touched files in diff: {len(touched_files)}")

    # 3. AST analysis — skip gracefully if file is missing or binary
    analyzer = UniversalASTAnalyzer()
    ast_map: Dict[str, Any] = {}
    skipped = 0
    for rel_path in touched_files:
        abs_path = os.path.join(repo_path, rel_path)
        if not os.path.isfile(abs_path):
            skipped += 1
            continue
        try:
            ast_map[rel_path] = analyzer.get_ast_skeleton(abs_path)
        except Exception:
            skipped += 1

    node_log.record(f"AST analysis: {len(ast_map)} files parsed, {skipped} skipped")

    # 4. Dependency scan
    dep_results = scan_dependencies(repo_path)
    codelens_dep_summary = _serialize_dep_scan(dep_results)
    total_warnings = sum(len(r.get("issues", [])) for r in dep_results)
    node_log.record(f"Dep-scan: {len(dep_results)} manifests, {total_warnings} warnings")

    # 5. Cross-reference search — find usages of touched module names
    max_search_files = Config.codelens_max_search_files()
    search_parts: List[str] = []
    seen_files = set(touched_files)
    for rel_path in touched_files[:max_search_files]:
        basename = os.path.splitext(os.path.basename(rel_path))[0]
        if not basename or basename in ("__init__", "index"):
            continue
        hits = find_text(repo_path, rf"\b{re.escape(basename)}\b", [".py", ".ts", ".js", ".java"])
        relevant = [h for h in hits[:8] if h["file"] not in seen_files]
        if relevant:
            search_parts.append(f"References to `{basename}`:")
            for h in relevant:
                search_parts.append(f"  {h['file']}:{h['line_number']}: {h['content']}")

    codelens_search_hits = "\n".join(search_parts) if search_parts else "(no cross-reference hits found)"
    node_log.record(
        f"Search hits: {len(search_parts)} lines (analyzed top {min(len(touched_files), max_search_files)} touched files, max_search_files={max_search_files})"
    )

    # Token counting for Codelens items
    ast_serialized = _serialize_ast_map(ast_map)
    ast_tokens = _count_tokens(ast_serialized)
    search_tokens = _count_tokens(codelens_search_hits)
    dep_tokens = _count_tokens(codelens_dep_summary)
    codelens_total_tokens = ast_tokens + search_tokens + dep_tokens

    node_log.record(
        f"Codelens Tokens: total={codelens_total_tokens} "
        f"(AST={ast_tokens}, Search={search_tokens}, DepScan={dep_tokens})"
    )

    # 6. Repository README loading & truncation
    readme_content = _load_readme_content(repo_path)
    node_log.record(f"README content: {len(readme_content)} chars")

    # 7. Partition diff into numbered regions for large PR review optimization
    max_lines = config.get("agents", {}).get("max_region_lines", 500)
    try:
        max_lines = int(max_lines)
    except (ValueError, TypeError):
        max_lines = 500

    file_diffs = split_diff_by_file(git_diff)
    regions = group_diffs_into_regions(file_diffs, max_lines)
    node_log.record(f"Diff partitioned into {len(regions)} review regions (max_region_lines={max_lines})")

    node_log.flush()

    return {
        "repo_structure": repo_structure,
        "ast_map": ast_map,
        "codelens_dep_summary": codelens_dep_summary,
        "codelens_search_hits": codelens_search_hits,
        "readme_content": readme_content,
        "regions": regions,
    }


# ---------------------------------------------------------------------------
# Agent nodes — Warden, Architect, Inspector
# ---------------------------------------------------------------------------

def _run_agent_node(
    state: ReviewState,
    agent_name: str,
    system_prompt: str,
    logger_name: str,
) -> Dict[str, Any]:
    """
    Shared execution body for all three agent nodes.

    Reads per-agent reasoning effort from config, assembles messages, calls
    the LLM, parses findings, and flushes the NodeLogger block.

    Args:
        state:         The current ``ReviewState`` dict.
        agent_name:    One of ``"warden"``, ``"architect"``, ``"inspector"``.
        system_prompt: The agent's persona prompt string (from ``prompts.py``).
        logger_name:   Fully-qualified logger name (e.g. ``"prism_reviewer.agents.warden"``).

    Returns:
        Partial state update: ``{"raw_findings": [...]}``.
    """
    logger = get_logger(logger_name)
    node_log = NodeLogger(logger, f"{agent_name.upper()} Node")

    # Resolve per-agent reasoning effort from config
    effort: str = (
        config.get("agents", {})
        .get("reasoning_effort", {})
        .get(agent_name, "medium")
    )
    model_name = Config.agent_model_name(agent_name)
    if not model_name:
        raise ValueError(
            f"No LLM model configured for agent '{agent_name}'. "
            "A model must be explicitly provided via LLM_MODEL_OVERRIDE or per-agent configuration."
        )
    node_log.record(f"Dispatching: model={model_name}, reasoning_effort={effort}")
    logger.info(
        f"[{agent_name.upper()} Node] Dispatched to model={model_name} "
        f"(reasoning_effort={effort}) — waiting for LLM response..."
    )

    user_turn = _build_user_turn(state, agent_name)

    # Calculate token breakdown per category for node logging
    sys_tokens = _count_tokens(system_prompt, model_name)
    ast_tokens = _count_tokens(_serialize_ast_map(state.get("ast_map", {})), model_name)
    search_tokens = _count_tokens(state.get("codelens_search_hits") or "", model_name)
    dep_tokens = _count_tokens(state.get("codelens_dep_summary") or "", model_name)
    codelens_subtotal = ast_tokens + search_tokens + dep_tokens

    repo_struct_tokens = _count_tokens(state.get("repo_structure") or "", model_name)
    readme_tokens = _count_tokens(state.get("readme_content") or "", model_name)
    context_tokens = _count_tokens(state.get("context_content") or "", model_name)
    rules_tokens = _count_tokens(state.get("rules_content") or "", model_name)

    pr_title_desc = f"Title: {state.get('pr_title') or ''}\nDescription:\n{state.get('pr_description') or ''}"
    pr_meta_tokens = _count_tokens(pr_title_desc, model_name)
    diff_tokens = _count_tokens(state.get("git_diff") or "", model_name)
    schema_tokens = _count_tokens(OUTPUT_SCHEMA_BLOCK, model_name)

    total_user_tokens = _count_tokens(user_turn, model_name)
    total_prompt_tokens = sys_tokens + total_user_tokens

    node_log.record(
        f"Prompt Token Breakdown (Total={total_prompt_tokens} tokens):\n"
        f"    [Codelens Data Tokens ({codelens_subtotal} tokens)]\n"
        f"      - AST Symbol Map:       {ast_tokens} tokens\n"
        f"      - Code Search Hits:     {search_tokens} tokens\n"
        f"      - Dependency Scan:      {dep_tokens} tokens\n"
        f"    [Other Prompt Category Tokens]\n"
        f"      - System Prompt:        {sys_tokens} tokens\n"
        f"      - Repo Structure:       {repo_struct_tokens} tokens\n"
        f"      - Repository README:    {readme_tokens} tokens\n"
        f"      - Project Context:      {context_tokens} tokens\n"
        f"      - Review Rules:         {rules_tokens} tokens\n"
        f"      - PR Metadata:          {pr_meta_tokens} tokens\n"
        f"      - Git Diff:             {diff_tokens} tokens\n"
        f"      - Output Schema:        {schema_tokens} tokens"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_turn},
    ]

    client = ResilientLLMClient(config._data)
    raw_response = client.completion_with_retry(messages, reasoning_effort=effort, model=model_name)
    logger.info(
        f"[{agent_name.upper()} Node] Received LLM response ({len(raw_response)} chars). Parsing findings..."
    )
    node_log.record(f"Response received: {len(raw_response)} chars")

    findings = _parse_findings(raw_response, agent_name, state["repo_path"], node_log)

    # Tally by severity for the log
    counts = {"CRITICAL": 0, "MAJOR": 0, "ADVISORY": 0}
    for f in findings:
        sev = f.get("severity", "ADVISORY")
        if sev in counts:
            counts[sev] += 1
    node_log.record(
        f"Parsed {len(findings)} findings "
        f"(CRITICAL={counts['CRITICAL']}, MAJOR={counts['MAJOR']}, ADVISORY={counts['ADVISORY']})"
    )

    node_log.flush()
    return {"raw_findings": findings}


def warden_node(state: ReviewState) -> Dict[str, Any]:
    """
    Warden agent node — security and compliance review.

    Runs in parallel with ``architect_node`` and ``inspector_node`` after
    ``build_context_node`` completes.  Uses ``reasoning_effort=high`` by default
    because security analysis benefits from deep chain-of-thought.

    Args:
        state: The current ``ReviewState`` dict.

    Returns:
        Partial state update: ``{"raw_findings": [...]}``.
    """
    return _run_agent_node(
        state,
        agent_name="warden",
        system_prompt=WARDEN_SYSTEM_PROMPT,
        logger_name="prism_reviewer.agents.warden",
    )


def architect_node(state: ReviewState) -> Dict[str, Any]:
    """
    Architect agent node — architecture and performance review.

    Runs in parallel with ``warden_node`` and ``inspector_node``.
    Uses ``reasoning_effort=medium`` by default.

    Args:
        state: The current ``ReviewState`` dict.

    Returns:
        Partial state update: ``{"raw_findings": [...]}``.
    """
    return _run_agent_node(
        state,
        agent_name="architect",
        system_prompt=ARCHITECT_SYSTEM_PROMPT,
        logger_name="prism_reviewer.agents.architect",
    )


def inspector_node(state: ReviewState) -> Dict[str, Any]:
    """
    Inspector agent node — clean code and logic review.

    Runs in parallel with ``warden_node`` and ``architect_node``.
    Uses ``reasoning_effort=medium`` by default.

    Args:
        state: The current ``ReviewState`` dict.

    Returns:
        Partial state update: ``{"raw_findings": [...]}``.
    """
    return _run_agent_node(
        state,
        agent_name="inspector",
        system_prompt=INSPECTOR_SYSTEM_PROMPT,
        logger_name="prism_reviewer.agents.inspector",
    )
