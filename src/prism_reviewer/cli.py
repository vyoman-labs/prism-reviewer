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
from .utils.git_utils import get_git_diff, get_repo_structure
from .utils.signature import get_finding_signature


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
            logger.error("No LLM model configuration is set. Please set LLM_MODEL_OVERRIDE.")
            sys.exit(1)
        if not Config.llm_api_key():
            logger.error("LLM API key is not set. Please set LLM_PROVIDER_API_KEY in .env or environment.")
            sys.exit(1)

        logger.info("PrismReviewer core process started.")
        logger.info(f"Repository: {repo_path}")
        logger.info(f"Base: {args.base or 'None'}")

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

        # Load previous signatures for idempotent deduplication
        signatures_dir = os.path.join(repo_path, ".prism_reviewer")
        signatures_path = os.path.join(signatures_dir, "signatures.json")
        previous_signatures: list[str] = []
        if os.path.exists(signatures_path):
            try:
                with open(signatures_path, "r", encoding="utf-8") as f:
                    previous_signatures = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load previous signatures: {e}")

        # Get git diff
        diff_base = args.base or "unstaged"
        diff_content = get_git_diff(repo_path, diff_base)

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

        # Persist signatures from verified findings for next-run deduplication
        new_signatures = [f["signature"] for f in verified_findings if f.get("signature")]
        os.makedirs(signatures_dir, exist_ok=True)
        try:
            with open(signatures_path, "w", encoding="utf-8") as f:
                json.dump(new_signatures, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save current signatures: {e}")

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
        logger.info("[cli] Core process completed.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()