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
    app_token: str | None = os.environ.get("GITHUB_APP_TOKEN")
    env_token: str | None = os.environ.get("GITHUB_TOKEN")
    token: str | None = app_token or env_token
    repo_name: str | None = os.environ.get("GITHUB_REPOSITORY")
    pr_number_str: str | None = os.environ.get("PR_NUMBER")
    report_file_path: str = os.environ.get("REPORT_FILE_PATH", "prism_review_report.md")

    if not token:
        logger.error("Environment variable GITHUB_TOKEN or GITHUB_APP_TOKEN is not set.")
        raise ValueError("GITHUB_TOKEN or GITHUB_APP_TOKEN must not be empty or None")

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

    if app_token:
        logger.info("Using GitHub App token (GITHUB_APP_TOKEN) to publish review comment.")
    else:
        logger.info("Using standard GitHub token (GITHUB_TOKEN) to publish review comment.")

    findings_file_path: str | None = os.environ.get("REPORT_FINDINGS_FILE_PATH")
    if not findings_file_path:
        report_dir = os.path.dirname(report_file_path)
        candidate1 = os.path.join(report_dir, "prism_review_findings.json") if report_dir else "prism_review_findings.json"
        candidate2 = os.path.join("reports", "prism_review_findings.json")
        if os.path.exists(candidate1):
            findings_file_path = candidate1
        elif os.path.exists(candidate2):
            findings_file_path = candidate2
        elif os.path.exists("prism_review_findings.json"):
            findings_file_path = "prism_review_findings.json"

    findings: list | None = None
    if findings_file_path and os.path.exists(findings_file_path):
        import json
        try:
            with open(findings_file_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    findings = loaded
                    logger.info(
                        f"Loaded {len(findings)} findings for inline comments from: {findings_file_path}"
                    )
        except Exception as e:
            logger.warning(f"Failed to read findings file at {findings_file_path}: {e}")

    logger.info(f"Connecting to GitHub PR #{pr_number} in repo '{repo_name}'...")
    bridge = GitHubAppBridge(token)
    bridge.publish_review_comment(repo_name, pr_number, markdown_body, findings=findings)
    logger.info("Successfully published review comment to GitHub PR.")

    # Only persist signatures for deduplication after comments are successfully published
    if findings:
        signatures_dir = os.path.join(os.getcwd(), ".prism_reviewer")
        signatures_path = os.path.join(signatures_dir, "signatures.json")
        os.makedirs(signatures_dir, exist_ok=True)
        posted_sigs: list[str] = [
            f["signature"] for f in findings if isinstance(f, dict) and f.get("signature")
        ]
        try:
            with open(signatures_path, "w", encoding="utf-8") as f:
                import json
                json.dump(posted_sigs, f, indent=2)
            logger.info(f"Persisted {len(posted_sigs)} posted finding signatures to {signatures_path}")
        except Exception as e:
            logger.warning(f"Failed to save posted signatures: {e}")


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
