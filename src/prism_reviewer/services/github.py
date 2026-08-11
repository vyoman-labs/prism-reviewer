import sys
import os
import requests

# Solve name collision with PyGithub library when PYTHONPATH contains the module folder
_our_module = sys.modules.pop('github', None)
_saved_sys_path = sys.path.copy()
sys.path = [
    p for p in sys.path 
    if not (p.endswith('prism_reviewer') or p.endswith('prism_reviewer\\') or p.endswith('prism_reviewer/'))
]
try:
    import github as PyGithub
    Github = PyGithub.Github
finally:
    sys.path = _saved_sys_path
    if _our_module is not None:
        sys.modules['github'] = _our_module

from typing import Any, Dict, List, Optional, cast


from ..core.logger import get_logger

logger = get_logger("prism_reviewer.services.github")



class GitHubAppBridge:
    """
    A bridge to interface with GitHub pull requests to extract diffs and publish comments.
    """

    def __init__(self, github_token: str):
        """
        Initializes the GitHubAppBridge with a GITHUB_TOKEN.
        
        Args:
            github_token: Personal access token or installation token.
        """
        if not github_token:
            raise ValueError("github_token must not be empty or None")
        self.token = github_token
        self.g = Github(auth=PyGithub.Auth.Token(github_token))

    def fetch_pull_request_diff(self, repo_name: str, pr_number: int) -> str:
        """
        Contacts the target workspace repository and pulls back the raw diff string.
        
        Args:
            repo_name: The full name of the repository (e.g. "owner/repo").
            pr_number: The pull request number.
            
        Returns:
            The raw diff text.
        """
        logger.info(f"Fetching diff for pull request #{pr_number} in repository {repo_name}")
        try:
            repo = self.g.get_repo(repo_name)
            pr = repo.get_pull(pr_number)

            # Attempt to fetch the raw diff directly via GitHub API
            try:
                headers = {
                    "Authorization": f"token {self.token}",
                    "Accept": "application/vnd.github.v3.diff",
                }
                logger.debug(f"Requesting raw diff from {pr.url}")
                response = requests.get(pr.url, headers=headers, timeout=30)
                response.raise_for_status()
                if response.text is None:
                    raise ValueError("Raw diff response text is None")
                return response.text
            except Exception as req_err:
                logger.warning(
                    f"Direct raw diff fetch failed: {req_err}. Falling back to patch reconstruction."
                )
                
                # Fallback: reconstruct diff from individual file patches
                patches = []
                for file in pr.get_files():
                    if file.patch:
                        patches.append(
                            f"diff --git a/{file.filename} b/{file.filename}\n"
                            f"index 0000000..0000000\n"
                            f"--- a/{file.filename}\n"
                            f"+++ b/{file.filename}\n"
                            f"{file.patch}"
                        )
                if patches:
                    return "\n".join(patches)
                
                raise req_err
        except Exception as e:
            logger.error(f"Failed to fetch pull request diff for {repo_name} #{pr_number}: {e}")
            raise RuntimeError(f"Failed to fetch pull request diff: {e}") from e

    def publish_review_comment(
        self,
        repo_name: str,
        pr_number: int,
        markdown_body: str,
        findings: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        """
        Publishes the aggregated review summary comment and inline review comments onto the PR.
        
        Args:
            repo_name: The full name of the repository (e.g. "owner/repo").
            pr_number: The pull request number.
            markdown_body: The review comments in markdown format.
            findings: Optional list of finding dicts to post as inline review comments.
            
        Returns:
            The created comment or review object.
        """
        logger.info(f"Publishing review comment to pull request #{pr_number} in repository {repo_name}")
        if not markdown_body:
            raise ValueError("markdown_body must not be empty or None")
        try:
            repo = self.g.get_repo(repo_name)
            pr = repo.get_pull(pr_number)

            inline_comments: List[Dict[str, Any]] = []
            if findings:
                from .. import __version__
                from ..utils.git_utils import normalize_file_path
                agent_emoji: Dict[str, str] = {
                    "warden": "👮",
                    "architect": "📐",
                    "inspector": "🔍",
                }
                severity_emoji: Dict[str, str] = {
                    "CRITICAL": "🚨",
                    "MAJOR": "⚠️",
                    "ADVISORY": "💡",
                }
                for f in findings:
                    file_path = f.get("file")
                    line_num = f.get("line")
                    if not file_path or not line_num:
                        continue
                    norm_path = normalize_file_path(str(file_path))
                    agent = str(f.get("agent", "unknown"))
                    severity = str(f.get("severity", "ADVISORY"))
                    msg = str(f.get("message", ""))

                    a_badge = agent_emoji.get(agent.lower(), "🤖")
                    s_badge = severity_emoji.get(severity, "💡")

                    body = (
                        f"{a_badge} **{agent.capitalize()}** ({s_badge} {severity})\n\n"
                        f"{msg}\n\n"
                        f"---\n"
                        f"*Prism Reviewer AI v{__version__}*"
                    )
                    inline_comments.append({
                        "path": norm_path,
                        "line": int(line_num),
                        "body": body,
                    })

            # In-memory deduplication
            unique_inline_comments: List[Dict[str, Any]] = []
            seen_keys: set[tuple[str, int, str]] = set()
            for c in inline_comments:
                key = (c["path"], c["line"], c["body"].strip())
                if key not in seen_keys:
                    seen_keys.add(key)
                    unique_inline_comments.append(c)
            inline_comments = unique_inline_comments

            # Fetch existing PR review comments to skip already published ones
            if inline_comments:
                try:
                    from ..utils.git_utils import normalize_file_path
                    existing_keys: set[tuple[str, int, str]] = set()
                    existing_review_comments = pr.get_review_comments()
                    for ec in existing_review_comments:
                        ec_path = normalize_file_path(str(ec.path)) if getattr(ec, "path", None) else ""
                        ec_line = getattr(ec, "line", None) or getattr(ec, "original_line", None) or 0
                        ec_body = str(getattr(ec, "body", "")).strip()
                        if ec_path and ec_line and ec_body:
                            existing_keys.add((ec_path, int(ec_line), ec_body))

                    if existing_keys:
                        fresh_inline_comments: List[Dict[str, Any]] = []
                        for c in inline_comments:
                            k = (c["path"], c["line"], c["body"].strip())
                            if k in existing_keys:
                                logger.info(
                                    f"Skipping inline comment at {c['path']}:{c['line']} - already published on PR."
                                )
                            else:
                                fresh_inline_comments.append(c)
                        inline_comments = fresh_inline_comments
                except Exception as fetch_err:
                    logger.warning(
                        f"Could not fetch existing PR review comments for deduplication: {fetch_err}"
                    )

            if inline_comments:
                try:
                    review = pr.create_review(
                        body=markdown_body,
                        comments=cast(Any, inline_comments),
                        event="COMMENT",
                    )

                    logger.info(f"Successfully published PR review with {len(inline_comments)} inline comments")
                    return review
                except Exception as inline_err:
                    logger.warning(
                        f"Failed batch PR review with {len(inline_comments)} inline comments: {inline_err}. Attempting individual comment submission."
                    )
                    valid_inline_comments: List[Dict[str, Any]] = []
                    for c in inline_comments:
                        try:
                            pr.create_review(comments=cast(Any, [c]), event="COMMENT")
                            valid_inline_comments.append(c)
                        except Exception as single_err:
                            logger.warning(
                                f"Skipping invalid inline comment at {c.get('path')}:{c.get('line')}: {single_err}"
                            )

                    if valid_inline_comments:
                        logger.info(
                            f"Successfully published {len(valid_inline_comments)} of {len(inline_comments)} inline comments individually."
                        )
                        comment = pr.create_issue_comment(markdown_body)
                        return comment

            comment = pr.create_issue_comment(markdown_body)
            logger.info(f"Successfully published comment ID {comment.id}")
            return comment
        except Exception as e:
            logger.error(f"Failed to publish review comment to {repo_name} #{pr_number}: {e}")
            raise RuntimeError(f"Failed to publish review comment: {e}") from e


    def fetch_pull_request_title(self, repo_name: str, pr_number: int) -> str:
        """
        Fetches the title of the pull request.
        
        Args:
            repo_name: The full name of the repository (e.g. "owner/repo").
            pr_number: The pull request number.
            
        Returns:
            The pull request title.
        """
        logger.info(f"Fetching title for pull request #{pr_number} in repository {repo_name}")
        try:
            repo = self.g.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            return pr.title
        except Exception as e:
            logger.error(f"Failed to fetch pull request title for {repo_name} #{pr_number}: {e}")
            raise RuntimeError(f"Failed to fetch pull request title: {e}") from e

    def fetch_pull_request_description(self, repo_name: str, pr_number: int) -> str:
        """
        Fetches the description (body) of the pull request.
        
        Args:
            repo_name: The full name of the repository (e.g. "owner/repo").
            pr_number: The pull request number.
            
        Returns:
            The pull request description, or empty string if None.
        """
        logger.info(f"Fetching description for pull request #{pr_number} in repository {repo_name}")
        try:
            repo = self.g.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            return pr.body or ""
        except Exception as e:
            logger.error(f"Failed to fetch pull request description for {repo_name} #{pr_number}: {e}")
            raise RuntimeError(f"Failed to fetch pull request description: {e}") from e

    def fetch_pull_request_details(self, repo_name: str, pr_number: int) -> Dict[str, Any]:
        """
        Fetches title, description, and number of the pull request in a single call.
        
        Args:
            repo_name: The full name of the repository (e.g. "owner/repo").
            pr_number: The pull request number.
            
        Returns:
            A dictionary containing 'title', 'description', and 'number'.
        """
        logger.info(f"Fetching PR details for #{pr_number} in repository {repo_name}")
        try:
            repo = self.g.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            return {
                "title": pr.title or "",
                "description": pr.body or "",
                "number": pr.number,
            }
        except Exception as e:
            logger.error(f"Failed to fetch pull request details for {repo_name} #{pr_number}: {e}")
            raise RuntimeError(f"Failed to fetch pull request details: {e}") from e

    def fetch_pull_requests_by_date(
        self,
        repo_name: str,
        start_date: str,
        end_date: str,
        date_type: str = "created",
    ) -> list:
        """
        Fetches pull requests for the specified repository within a date range.
        
        Args:
            repo_name: The full name of the repository (e.g. "owner/repo").
            start_date: Start date string (e.g. "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SSZ").
            end_date: End date string (e.g. "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SSZ").
            date_type: The date field to filter by ("created", "updated", or "merged"). Defaults to "created".
            
        Returns:
            A list of PyGithub PullRequest objects.
        """
        logger.info(
            f"Fetching pull requests for {repo_name} with {date_type} date range: {start_date} to {end_date}"
        )
        if date_type not in ("created", "updated", "merged"):
            raise ValueError("date_type must be one of 'created', 'updated', 'merged'")
        
        try:
            query = f"is:pr repo:{repo_name} {date_type}:{start_date}..{end_date}"
            logger.debug(f"Executing GitHub search with query: {query}")
            results = self.g.search_issues(query=query)
            
            pulls = []
            for issue in results:
                try:
                    pulls.append(issue.as_pull_request())
                except Exception as e:
                    logger.warning(f"Could not cast issue #{issue.number} to pull request: {e}")
                    pulls.append(issue)
            return pulls
        except Exception as e:
            logger.error(f"Failed to fetch pull requests by date for {repo_name}: {e}")
            raise RuntimeError(f"Failed to fetch pull requests by date: {e}") from e
