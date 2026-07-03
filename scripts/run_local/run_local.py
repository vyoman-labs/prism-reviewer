#!/usr/bin/env python
"""
run_local.py
~~~~~~~~~~~~
A utility script to fetch a pull request's diff, title, and description from
GitHub using a Pull Request ID and run the Prism Reviewer agentic review flow
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
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub Personal Access Token (defaults to GITHUB_TOKEN env variable)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="prism_review_report.md",
        help="Output filepath for the Markdown review report (default: prism_review_report.md)",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    logger = get_logger("prism_reviewer.run_local")

    if not args.token:
        logger.error("GitHub access token is required. Set GITHUB_TOKEN or pass via --token.")
        sys.exit(1)

    # Load system configuration
    try:
        Config.load()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Ensure model and api_key are configured
    model_name = Config.llm_model_name()
    api_key = Config.llm_api_key()
    if not model_name:
        logger.error("LLM_MODEL_NAME is not set in config or environment.")
        sys.exit(1)
    if not api_key:
        logger.error("LLM_MODEL_API_KEY (or LLM_PROVIDER_API_KEY) is not set.")
        sys.exit(1)

    logger.info(f"Initializing GitHub Bridge for {args.repo}...")
    try:
        bridge = GitHubAppBridge(args.token)
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

    # Build initial State for LangGraph
    initial_state: Dict[str, Any] = {
        "repo_path": os.getcwd(),
        "git_diff": git_diff,
        "pr_title": pr_title,
        "pr_description": pr_description,
        "repo_structure": "",
        "ast_map": {},
        "codelens_dep_summary": "",
        "codelens_search_hits": "",
        "context_content": "",
        "rules_content": "",
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

    # Execute LangGraph review council
    logger.info("Executing parallel review council agents...")
    try:
        final_state = graph.invoke(initial_state)
    except Exception as e:
        logger.error(f"Error during graph execution: {e}")
        sys.exit(1)

    report_markdown = final_state.get("report_markdown", "")
    if not report_markdown:
        logger.warning("No review report was generated.")
        sys.exit(0)

    # Save report locally
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_markdown)
        logger.info(f"Local PR review report saved to: {args.output}")
    except Exception as e:
        logger.error(f"Failed to write report to {args.output}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
