"""
Helper script to publish the generated review report to the GitHub PR.
"""

import os
import sys

from prism_reviewer.core.logger import get_logger
from prism_reviewer.services.github import GitHubAppBridge

logger = get_logger("prism_reviewer.post_review")


def publish_report_to_pr() -> None:
    """
    Reads the generated prism_review_report.md and posts it to the target GitHub PR.

    Raises:
        ValueError: If required environment variables are missing or invalid.
        FileNotFoundError: If the report markdown file does not exist.
        RuntimeError: If publishing the review comment fails.
    """
    token: str | None = os.environ.get("GITHUB_TOKEN")
    repo_name: str | None = os.environ.get("GITHUB_REPOSITORY")
    pr_number_str: str | None = os.environ.get("PR_NUMBER")
    report_file_path: str = os.environ.get("REPORT_FILE_PATH", "prism_review_report.md")

    if not token:
        logger.error("Environment variable GITHUB_TOKEN is not set.")
        raise ValueError("GITHUB_TOKEN must not be empty or None")

    if not repo_name:
        logger.error("Environment variable GITHUB_REPOSITORY is not set.")
        raise ValueError("GITHUB_REPOSITORY must not be empty or None")

    if not pr_number_str:
        logger.error("Environment variable PR_NUMBER is not set.")
        raise ValueError("PR_NUMBER must not be empty or None")

    try:
        pr_number: int = int(pr_number_str)
    except ValueError as e:
        logger.error(f"PR_NUMBER '{pr_number_str}' is not a valid integer.")
        raise ValueError(f"PR_NUMBER must be a valid integer: {e}") from e

    if not os.path.exists(report_file_path):
        logger.error(f"Report file not found at: {report_file_path}")
        raise FileNotFoundError(f"Report file not found: {report_file_path}")

    with open(report_file_path, "r", encoding="utf-8") as f:
        markdown_body: str = f.read()

    if not markdown_body.strip():
        logger.warning("Markdown report is empty. Skipping post to GitHub.")
        return

    logger.info(f"Connecting to GitHub PR #{pr_number} in repo '{repo_name}'...")
    bridge = GitHubAppBridge(token)
    bridge.publish_review_comment(repo_name, pr_number, markdown_body)
    logger.info("Successfully published review comment to GitHub PR.")


def main() -> None:
    """
    CLI Entrypoint for the post_review script.
    """
    try:
        publish_report_to_pr()
    except Exception as e:
        logger.error(f"Error publishing review report: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
