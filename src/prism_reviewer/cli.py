import argparse
import json
import os
import sys
import time as _time
from typing import Any

from .agents.graph import build_graph
from .agents.state import ReviewState
from .core.config import Config, config
from .core.logger import get_logger
from .codelens.dependency_scanner import scan_dependencies
from .codelens.searcher import find_text, get_full_file, get_related_files, get_file_methods
from .utils.git_utils import (
    get_changed_files_list,
    get_current_head_sha,
    get_git_diff,
    get_repo_structure,
)

from .utils.signature import get_finding_signature
from .monitoring.manager import monitoring_manager


def _resolve_pr_api_details(repo_path: str, logger: Any) -> tuple[str, str, int | None]:
    """
    Attempts to fetch PR title, description, and ID from the GitHub API using environment
    variables or git repository remote information.

    Returns:
        tuple of (pr_title, pr_description, pr_id)
    """
    app_token = os.environ.get("GITHUB_APP_TOKEN")
    env_token = os.environ.get("GITHUB_TOKEN")
    config_token = Config.github_token()

    token = app_token or env_token or config_token
    if not token:
        logger.warning("No GITHUB_TOKEN or GITHUB_APP_TOKEN set; skipping fetching PR details from GitHub API.")
        return "", "", None

    if app_token:
        logger.info("Using GitHub App token (GITHUB_APP_TOKEN) to fetch PR details from GitHub API.")
    elif env_token:
        logger.info("Using standard GitHub token (GITHUB_TOKEN) to fetch PR details from GitHub API.")
    else:
        logger.info("Using configured GitHub token to fetch PR details from GitHub API.")

    repo_name = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo_name:
        try:
            import subprocess
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=False,
            )
            url = result.stdout.strip()
            if url and "github.com" in url:
                cleaned = url.split("github.com")[-1].lstrip(":/")
                if cleaned.endswith(".git"):
                    cleaned = cleaned[:-4]
                repo_name = cleaned
        except Exception as e:
            logger.debug(f"Failed to infer repository name from git remote: {e}")

    if not repo_name:
        logger.warning("Could not determine repository name; skipping fetching PR details from GitHub API.")
        return "", "", None

    pr_number_str = os.environ.get("PR_NUMBER")
    if not pr_number_str:
        import re
        github_ref = os.environ.get("GITHUB_REF", "")
        match = re.search(r"refs/pull/(\d+)", github_ref)
        if match:
            pr_number_str = match.group(1)

    if not pr_number_str:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if event_path and os.path.exists(event_path):
            try:
                with open(event_path, "r", encoding="utf-8") as f:
                    event_data = json.load(f)
                    if isinstance(event_data, dict) and "pull_request" in event_data:
                        pr_number_str = str(event_data["pull_request"].get("number", ""))
            except Exception as e:
                logger.debug(f"Failed to parse GITHUB_EVENT_PATH: {e}")

    if not pr_number_str:
        logger.warning("Could not determine PR number; skipping fetching PR details from GitHub API.")
        return "", "", None

    try:
        pr_number = int(pr_number_str)
    except ValueError:
        logger.warning(f"Invalid PR number format: '{pr_number_str}'")
        return "", "", None

    try:
        from .services.github import GitHubAppBridge
        bridge = GitHubAppBridge(token)
        details = bridge.fetch_pull_request_details(repo_name, pr_number)
        logger.info(f"Successfully fetched PR #{pr_number} details from API: '{details.get('title')}'")
        return details.get("title", ""), details.get("description", ""), pr_number
    except Exception as e:
        logger.warning(f"Failed to fetch PR details from GitHub API: {e}")
        return "", "", pr_number


def _resolve_git_diff_mode_and_content(
    repo_path: str,
    args: Any,
    logger: Any,
) -> tuple[str, bool, str, list[str], str]:
    """
    Resolves git diff content, incremental status, configured diff mode, full PR files list,
    and current HEAD commit SHA based on configuration and CLI parameters.

    Returns:
        (diff_content, is_incremental, configured_mode, full_pr_files, current_head_sha)
    """
    mode = (getattr(args, "diff_mode", None) or Config.diff_mode()).lower()
    if mode not in ("auto", "full", "incremental"):
        mode = "auto"

    diff_base = getattr(args, "compare_range", None) or getattr(args, "base", None) or "unstaged"
    current_head = get_current_head_sha(repo_path)

    # Load persistent state if available
    signatures_dir = os.path.join(repo_path, ".prism_reviewer")
    state_path = os.path.join(signatures_dir, "state.json")
    last_reviewed_sha = ""
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                saved_state = json.load(f)
                if isinstance(saved_state, dict):
                    last_reviewed_sha = str(saved_state.get("last_reviewed_commit_sha", ""))
        except Exception as exc:
            logger.debug(f"Failed to read state.json: {exc}")

    # Check GitHub Actions event for previous commit SHA if not in local state
    if not last_reviewed_sha:
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if event_path and os.path.exists(event_path):
            try:
                with open(event_path, "r", encoding="utf-8") as f:
                    event_data = json.load(f)
                    if isinstance(event_data, dict):
                        last_reviewed_sha = str(event_data.get("before", ""))
            except Exception as exc:
                logger.debug(f"Failed to extract 'before' commit from GITHUB_EVENT_PATH: {exc}")

    full_pr_files = get_changed_files_list(repo_path, diff_base) if diff_base != "unstaged" else []

    if mode in ("auto", "incremental"):
        prev_sha = last_reviewed_sha
        if prev_sha and current_head and prev_sha != current_head:
            logger.info(f"[cli] Attempting incremental review diff from {prev_sha[:7]}..{current_head[:7]}")
            inc_diff = get_git_diff(repo_path, f"{prev_sha}..{current_head}")
            if inc_diff.strip():
                logger.info(f"[cli] Using incremental diff ({len(inc_diff.splitlines())} lines)")
                return inc_diff, True, mode, full_pr_files, current_head
            else:
                logger.info("[cli] Incremental diff was empty; falling back to full diff.")

        if mode == "incremental" and not last_reviewed_sha:
            logger.warning("[cli] Incremental diff requested but no previous commit SHA found. Falling back to full diff.")

    logger.info(f"[cli] Using full diff mode with base '{diff_base}'")
    full_diff = get_git_diff(repo_path, diff_base)
    return full_diff, False, mode, full_pr_files, current_head


def main(argv=None):

    parser = argparse.ArgumentParser(
        prog="prism-review",
        description="PrismReviewer command-line interface"
    )
    parser.add_argument(
        "--pr",
        action="store_true",
        help="Run the PrismReviewer core process"
    )
    parser.add_argument(
        "--repo",
        type=str,
        required=False,
        help="Path to the repository to review"
    )
    parser.add_argument(
        "--base",
        type=str,
        required=False,
        help="Base branch or commit for comparison"
    )
    parser.add_argument(
        "--diff",
        nargs="?",
        const="unstaged",
        type=str,
        help="Get local git diff. Can specify commit/branch, 'staged', or 'unstaged' (default)."
    )
    parser.add_argument(
        "--structure",
        action="store_true",
        help="Display repository directory structure of tracked files"
    )
    parser.add_argument(
        "--scan-deps",
        action="store_true",
        help="Scan project manifest files for dependencies and configuration warnings"
    )
    parser.add_argument(
        "--search",
        type=str,
        help="Regex search query to find occurrences in repository"
    )
    parser.add_argument(
        "--ext",
        type=str,
        help="Comma-separated file extensions to filter search results (e.g. .py,.js)"
    )
    parser.add_argument(
        "--file-content",
        type=str,
        help="Print the full content of a specific file in the repository"
    )
    parser.add_argument(
        "--related",
        type=str,
        help="List files related to the specified file"
    )
    parser.add_argument(
        "--methods",
        type=str,
        help="Extract and print AST symbols (classes, functions, methods) from the file"
    )
    parser.add_argument(
        "--context",
        type=str,
        required=False,
        help="Path to optional project context markdown file"
    )
    parser.add_argument(
        "--rules",
        type=str,
        required=False,
        help="Path to optional rules markdown file"
    )
    parser.add_argument(
        "--diff-mode",
        type=str,
        choices=["auto", "full", "incremental"],
        required=False,
        help="Git diff strategy for review ('auto', 'full', or 'incremental'). Defaults to config."
    )
    parser.add_argument(
        "--compare-range",
        type=str,
        required=False,
        help="Explicit commit range or base for comparison (e.g. SHA1..SHA2 or origin/main)"
    )


    args = parser.parse_args(argv)

    logger = get_logger()

    # Determine repository path
    repo_path = args.repo or os.getcwd()

    # Load configuration
    try:
        Config.load()
        logger.debug("Configuration loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # 1. Diff Tool
    if args.diff is not None:
        try:
            diff = get_git_diff(repo_path, args.diff)
            print(diff)
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error getting diff: {e}")
            sys.exit(1)

    # 2. Structure Tool
    if args.structure:
        try:
            structure = get_repo_structure(repo_path)
            print(json.dumps(structure, indent=2))
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error getting structure: {e}")
            sys.exit(1)

    # 3. Dependency Scanner
    if args.scan_deps:
        try:
            results = scan_dependencies(repo_path)
            print(json.dumps(results, indent=2))
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error scanning dependencies: {e}")
            sys.exit(1)

    # 4. Regex/Text Searcher
    if args.search:
        try:
            ext_filter = [x.strip() for x in args.ext.split(",")] if args.ext else None
            results = find_text(repo_path, args.search, ext_filter)
            print(json.dumps(results, indent=2))
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error performing search: {e}")
            sys.exit(1)

    # 5. File Content Reader
    if args.file_content:
        try:
            content = get_full_file(repo_path, args.file_content)
            print(content)
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error reading file content: {e}")
            sys.exit(1)

    # 6. Related Files
    if args.related:
        try:
            related = get_related_files(repo_path, args.related)
            print(json.dumps(related, indent=2))
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error finding related files: {e}")
            sys.exit(1)

    # 7. AST Methods Extractor
    if args.methods:
        try:
            symbols = get_file_methods(repo_path, args.methods)
            print(json.dumps(symbols, indent=2))
            sys.exit(0)
        except Exception as e:
            logger.error(f"Error extracting methods: {e}")
            sys.exit(1)

    if args.pr:
        has_model = bool(
            Config.llm_model_name()
            or any(Config.agent_model_name(agent) for agent in ["warden", "architect", "inspector"])
        )
        if not has_model:
            logger.error("No LLM model configuration is set. Please set LLM_MODEL.")
            sys.exit(1)
        if not Config.llm_api_key():
            logger.error("LLM API key is not set. Please set LLM_PROVIDER_API_KEY in .env or environment.")
            sys.exit(1)

        logger.info("[cli] PrismReviewer core process started.")
        logger.info(f"[cli] Repository: {repo_path}")
        logger.info(f"[cli] Base: {args.base or 'None'}")

        # Resolve optional project context file
        context_path = args.context
        if not context_path:
            default_context = os.path.join(repo_path, ".prism_reviewer", "context.md")
            if os.path.exists(default_context):
                context_path = default_context

        context_content = ""
        if context_path and os.path.exists(context_path):
            with open(context_path, "r", encoding="utf-8") as f:
                context_content = f.read()

        # Resolve optional rules file
        rules_path = args.rules
        if not rules_path:
            default_rules = os.path.join(repo_path, ".prism_reviewer", "rules.md")
            if os.path.exists(default_rules):
                rules_path = default_rules

        rules_content = ""
        if rules_path and os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as f:
                rules_content = f.read()

        # Load previous state and signatures for idempotent deduplication and incremental diffs
        signatures_dir = os.path.join(repo_path, ".prism_reviewer")
        signatures_path = os.path.join(signatures_dir, "signatures.json")
        state_path = os.path.join(signatures_dir, "state.json")
        previous_signatures: list[str] = []
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    saved_state = json.load(f)
                    if isinstance(saved_state, dict) and "signatures" in saved_state:
                        previous_signatures = saved_state["signatures"]
            except Exception as e:
                logger.warning(f"Failed to load previous state.json: {e}")

        if not previous_signatures and os.path.exists(signatures_path):
            try:
                with open(signatures_path, "r", encoding="utf-8") as f:
                    previous_signatures = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load previous signatures: {e}")

        # Resolve git diff content and incremental mode
        diff_content, is_incremental, diff_mode_used, full_pr_files, current_head_sha = _resolve_git_diff_mode_and_content(
            repo_path, args, logger
        )

        # Always attempt to fetch PR title, description, and ID from GitHub API
        pr_title, pr_description, pr_id = _resolve_pr_api_details(repo_path, logger)

        # Build initial state — build_context_node will populate the codelens fields
        initial_state: ReviewState = {
            "repo_path": repo_path,
            "git_diff": diff_content,
            "pr_title": pr_title,
            "pr_description": pr_description,
            "repo_structure": "",
            "ast_map": {},
            "codelens_dep_summary": "",
            "codelens_search_hits": "",
            "context_content": context_content,
            "readme_content": "",
            "rules_content": rules_content,
            "previous_signatures": previous_signatures,
            "raw_findings": [],
            "verified_findings": [],
            "report_markdown": "",
            "regions": [],
            "diff_mode": diff_mode_used,
            "is_incremental": is_incremental,
            "full_pr_files": full_pr_files,
        }
        if pr_id is not None:
            initial_state["pr_id"] = pr_id

        # Run the multi-agent graph using stream() for structured per-node events
        graph = build_graph()
        logger.info("[cli] Review graph started")

        review_start = _time.monotonic()
        final_state: dict = dict(initial_state)
        final_state["raw_findings"] = []
        final_state["verified_findings"] = []

        for event in graph.stream(initial_state, stream_mode="updates"):
            for node_name, node_output in event.items():
                logger.info(f"[cli] Node '{node_name}' completed")
                for k, v in node_output.items():
                    if k == "raw_findings":
                        final_state["raw_findings"].extend(v)
                    else:
                        final_state[k] = v

        total_time = _time.monotonic() - review_start
        logger.info(f"[cli] Review complete — total execution time: {total_time:.2f}s")

        report_markdown: str = final_state.get("report_markdown", "")
        verified_findings: list = final_state.get("verified_findings", [])

        # Persist state and signatures
        new_signatures = [f["signature"] for f in verified_findings if f.get("signature")]
        combined_signatures = list(dict.fromkeys(previous_signatures + new_signatures))
        os.makedirs(signatures_dir, exist_ok=True)
        try:
            state_data = {
                "last_reviewed_commit_sha": current_head_sha,
                "signatures": combined_signatures if pr_id is None else new_signatures,
            }
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2)
            with open(signatures_path, "w", encoding="utf-8") as f:
                json.dump(state_data["signatures"], f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state and signatures: {e}")


        # Write the Markdown report to disk atomically inside reports/ directory
        reports_dir = os.path.join(repo_path, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        report_path = os.path.join(reports_dir, "prism_review_report.md")
        temp_report_path = f"{report_path}.tmp"
        with open(temp_report_path, "w", encoding="utf-8") as f:
            f.write(report_markdown)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_report_path, report_path)

        # Write verified findings JSON artifact atomically
        findings_path = os.path.join(reports_dir, "prism_review_findings.json")
        temp_findings_path = f"{findings_path}.tmp"
        with open(temp_findings_path, "w", encoding="utf-8") as f:
            json.dump(verified_findings, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_findings_path, findings_path)

        logger.info(f"[cli] Review report generated at: {report_path}")
        logger.info(f"[cli] Verified findings artifact generated at: {findings_path}")

        # Flush active LiteLLM observability callbacks (e.g. Langfuse)
        monitoring_manager.flush_callbacks()

        logger.info("[cli] Core process completed.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()