#!/usr/bin/env python
"""
run_local.py
~~~~~~~~~~~~
A utility script to fetch a pull request's diff, title, and description from
GitHub using a Pull Request ID and run the Prism Reviewer AI agentic review flow
locally.

Requirements:
- Install the package in editable mode: pip install -e .
- Set GITHUB_TOKEN (or pass via --token)
- Set LLM_PROVIDER_API_KEY and LLM_MODEL_NAME
"""

import argparse
import os
import sys
from typing import Any, Dict

# Ensure we can import prism_reviewer package from the source directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(project_root, "src"))

try:
    from prism_reviewer import build_graph, GitHubAppBridge
    from prism_reviewer.core.config import Config
    from prism_reviewer.core.logger import get_logger
except ImportError as e:
    print(f"Error importing Prism Reviewer: {e}")
    print("Ensure the package is installed: pip install -e .")
    sys.exit(1)


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Run Prism Reviewer locally for a remote GitHub Pull Request ID."
    )
    parser.add_argument(
        "--repo",
        type=str,
        required=True,
        help="Full repository name on GitHub (e.g., 'owner/repository')",
    )
    parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="Pull Request ID number",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="GitHub Personal Access Token (defaults to GITHUB_TOKEN in .env or environment)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output filepath for the Markdown review report (defaults to PR-specific name e.g. prism_review_report_apache_ranger_pr1139.md)",
    )
    parser.add_argument(
        "--context",
        type=str,
        required=False,
        help="Path to optional project context markdown file (defaults to .prism_reviewer/context.md)",
    )
    parser.add_argument(
        "--rules",
        type=str,
        required=False,
        help="Path to optional rules markdown file (defaults to .prism_reviewer/rules.md)",
    )
    return parser.parse_args()


def _write_atomic_file(filepath: str, content: str) -> None:
    """Writes content to a file atomically to prevent editors from seeing truncated states."""
    parent_dir = os.path.dirname(filepath)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    temp_path = f"{filepath}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp_path, filepath)


def main():
    args = parse_arguments()
    logger = get_logger("prism_reviewer.run_local")

    # Load system configuration (loads .env and prism_reviewer.toml)
    try:
        Config.load()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    github_token = args.token or Config.github_token()
    if not github_token:
        logger.error("GitHub access token is required. Set GITHUB_TOKEN in .env or pass via --token.")
        sys.exit(1)

    # Ensure model and api_key are configured
    model_name = Config.llm_model_name()
    api_key = Config.llm_api_key()
    if not model_name:
        logger.error("LLM_MODEL_NAME (or LLM_MODEL_OVERRIDE) is not set in .env, config, or environment.")
        sys.exit(1)
    if not api_key:
        logger.error("LLM_PROVIDER_API_KEY (or LLM_MODEL_API_KEY) is not set in .env, config, or environment.")
        sys.exit(1)

    logger.info(f"Initializing GitHub Bridge for {args.repo}...")
    try:
        bridge = GitHubAppBridge(github_token)
    except Exception as e:
        logger.error(f"Failed to initialize GitHub bridge: {e}")
        sys.exit(1)

    # Fetch Pull Request details
    try:
        logger.info(f"Fetching Pull Request #{args.pr} details...")
        git_diff = bridge.fetch_pull_request_diff(args.repo, args.pr)
        pr_title = bridge.fetch_pull_request_title(args.repo, args.pr)
        pr_description = bridge.fetch_pull_request_description(args.repo, args.pr)
        logger.info(f"Successfully retrieved PR: '{pr_title}'")
    except Exception as e:
        logger.error(f"Failed to retrieve Pull Request details from GitHub: {e}")
        sys.exit(1)

    repo_path = os.getcwd()

    # Resolve optional project context file
    context_path = args.context
    if not context_path:
        default_context = os.path.join(repo_path, ".prism_reviewer", "context.md")
        if os.path.exists(default_context):
            context_path = default_context

    context_content = ""
    if context_path and os.path.exists(context_path):
        try:
            with open(context_path, "r", encoding="utf-8") as f:
                context_content = f.read()
            logger.info(f"Loaded project context from: {context_path}")
        except Exception as e:
            logger.warning(f"Failed to read project context at {context_path}: {e}")

    # Resolve optional rules file
    rules_path = args.rules
    if not rules_path:
        default_rules = os.path.join(repo_path, ".prism_reviewer", "rules.md")
        if os.path.exists(default_rules):
            rules_path = default_rules

    rules_content = ""
    if rules_path and os.path.exists(rules_path):
        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                rules_content = f.read()
            logger.info(f"Loaded review rules from: {rules_path}")
        except Exception as e:
            logger.warning(f"Failed to read review rules at {rules_path}: {e}")

    # Build initial State for LangGraph
    initial_state: Dict[str, Any] = {
        "repo_path": repo_path,
        "git_diff": git_diff,
        "pr_title": pr_title,
        "pr_id": args.pr,
        "pr_description": pr_description,
        "repo_structure": "",
        "ast_map": {},
        "codelens_dep_summary": "",
        "codelens_search_hits": "",
        "context_content": context_content,
        "rules_content": rules_content,
        "previous_signatures": [],
        "raw_findings": [],
        "verified_findings": [],
        "report_markdown": "",
        "regions": [],
    }

    # Compile the graph
    logger.info("Assembling and compiling the review graph flow...")
    try:
        graph = build_graph()
    except Exception as e:
        logger.error(f"Failed to assemble the graph: {e}")
        sys.exit(1)

    # Execute LangGraph review council with live streaming node completion logs
    import time as _time
    logger.info("Executing parallel review council agents...")
    review_start = _time.monotonic()
    final_state: Dict[str, Any] = dict(initial_state)
    final_state["raw_findings"] = []
    final_state["verified_findings"] = []

    try:
        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                logger.info(f"[run_local] Node '{node_name}' completed execution.")
                for k, v in node_output.items():
                    if k == "raw_findings":
                        final_state["raw_findings"].extend(v)
                    else:
                        final_state[k] = v
    except Exception as e:
        logger.error(f"Error during graph execution: {e}")
        sys.exit(1)

    total_time = _time.monotonic() - review_start
    logger.info(f"[run_local] Review complete — total execution time: {total_time:.2f}s")

    report_markdown = final_state.get("report_markdown", "")
    if not report_markdown:
        logger.warning("No review report was generated.")
        sys.exit(0)

    # Save report inside reports/ folder
    reports_dir = os.path.join(repo_path, "reports")
    os.makedirs(reports_dir, exist_ok=True)

    if args.output:
        if os.path.isabs(args.output) or os.path.dirname(args.output):
            primary_output = args.output
        else:
            primary_output = os.path.join(reports_dir, args.output)
    else:
        safe_repo = args.repo.replace("/", "_").replace("\\", "_")
        primary_output = os.path.join(reports_dir, f"prism_review_report_{safe_repo}_pr{args.pr}.md")

    latest_output = os.path.join(reports_dir, "prism_review_report.md")

    # Save report locally to the specific PR report path using atomic file writing
    try:
        _write_atomic_file(primary_output, report_markdown)
        logger.info(f"Local PR review report saved to: {primary_output}")

        # Also update reports/prism_review_report.md for convenience if primary is distinct
        if primary_output != latest_output:
            _write_atomic_file(latest_output, report_markdown)
            logger.info(f"Updated latest review report copy at: {latest_output}")

        # Save verified findings artifact
        verified_findings = final_state.get("verified_findings", [])
        import json
        findings_json = json.dumps(verified_findings, indent=2)
        findings_output = os.path.join(reports_dir, "prism_review_findings.json")
        _write_atomic_file(findings_output, findings_json)
        logger.info(f"Local PR verified findings saved to: {findings_output}")
    except Exception as e:
        logger.error(f"Failed to write report or findings to {primary_output}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
