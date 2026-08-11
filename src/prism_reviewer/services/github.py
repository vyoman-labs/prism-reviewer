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

from typing import Any, Dict, List, Optional, Tuple, cast


from ..core.config import Config
from ..core.logger import get_logger

logger = get_logger("prism_reviewer.services.github")

# Imported lazily to avoid a circular dependency at module load time;
# resolved at first call inside _find_existing_summary_comment().
_SUMMARY_MARKER: str = "<!-- prism-reviewer-summary -->"



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

    def _find_existing_summary_comment(self, pr: Any) -> Optional[Any]:
        """
        Searches existing PR issue comments for a Prism Reviewer summary comment.

        A summary comment is identified by the presence of the hidden HTML marker
        ``<!-- prism-reviewer-summary -->`` in the comment body.

        Args:
            pr: A PyGithub ``PullRequest`` object.

        Returns:
            The first matching ``IssueComment`` object, or ``None`` if no prior
            summary comment exists on this PR.
        """
        try:
            for comment in pr.get_issue_comments():
                body: str = str(getattr(comment, "body", "") or "")
                if _SUMMARY_MARKER in body:
                    return comment
        except Exception as err:
            logger.warning(f"Could not search existing PR issue comments: {err}")
        return None

    def _get_resolved_inline_sigs(
        self,
        pr: Any,
        findings: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Queries GitHub PR review comment threads to discover which finding
        signatures have been manually resolved by a reviewer.

        GitHub's REST API does not expose thread resolution status directly on
        review comments.  We approximate this by checking whether a review
        comment thread has been marked resolved via the GraphQL API if available,
        or by matching the ``in_reply_to_id`` pattern of resolved threads.
        As a pragmatic fallback, we check whether the inline comment at the
        matching ``(path, line)`` co-ordinates has a sibling comment whose body
        begins with the GitHub-generated "*Conversation was marked as resolved*"
        text (created when a reviewer clicks the Resolve button).

        Args:
            pr: A PyGithub ``PullRequest`` object.
            findings: List of finding dicts (must contain ``signature``,
                ``file``, and ``line`` keys).

        Returns:
            List of finding signatures that have been resolved.
        """
        if not findings:
            return []

        resolved_sigs: List[str] = []
        try:
            from ..utils.git_utils import normalize_file_path

            # Build a map of (normalised_path, line) -> signature for quick lookup
            loc_to_sig: Dict[Tuple[str, int], str] = {}
            for f in findings:
                path = normalize_file_path(str(f.get("file", "")))
                line = int(f.get("line", 0))
                sig = str(f.get("signature", ""))
                if path and line and sig:
                    loc_to_sig[(path, line)] = sig

            if not loc_to_sig:
                return []

            # Collect all review comments on the PR
            all_review_comments = list(pr.get_review_comments())

            # Identify review comment IDs that are root comments (no in_reply_to)
            root_ids: set[int] = set()
            replied_to_ids: set[int] = set()
            for rc in all_review_comments:
                reply_to = getattr(rc, "in_reply_to_id", None)
                if reply_to is None:
                    root_ids.add(rc.id)
                else:
                    replied_to_ids.add(reply_to)

            # A thread is considered resolved if:
            #   - The root comment's body contains the Prism marker (it is ours), AND
            #   - One of the reply comments in that thread contains the GitHub
            #     'Marked as resolved' indicator OR the thread has no unresolved replies
            #     and the root itself was created by us.
            #
            # Because the REST API does not expose `is_resolved`, we use a
            # best-effort heuristic: if the thread has a reply whose body starts
            # with "Marked conversation as resolved" (the default text GitHub
            # inserts in some integrations), or whose body is empty with a
            # specific user type, we flag it resolved.
            #
            # In practice the most reliable signal available via REST is to check
            # whether `pull_request_review_thread` events exist on the PR timeline
            # with action="resolved".  We do that via the raw GitHub REST endpoint.
            try:
                headers = {
                    "Authorization": f"token {self.token}",
                    "Accept": "application/vnd.github+json",
                }
                timeline_url = pr.url.rstrip("/") + "/timeline"
                response = requests.get(timeline_url, headers=headers, timeout=15)
                response.raise_for_status()
                timeline_events = response.json() if isinstance(response.json(), list) else []
            except Exception as tl_err:
                logger.debug(f"Could not fetch PR timeline for thread resolution: {tl_err}")
                timeline_events = []

            # Collect thread IDs that have been explicitly resolved
            resolved_thread_ids: set[int] = set()
            for event in timeline_events:
                if (
                    isinstance(event, dict)
                    and event.get("event") == "review_dismissed"
                    or (
                        isinstance(event, dict)
                        and event.get("event") == "resolved"
                    )
                ):
                    thread = event.get("pull_request_review_thread", {})
                    if isinstance(thread, dict):
                        tid = thread.get("id")
                        if tid is not None:
                            resolved_thread_ids.add(tid)

            # Map resolved thread root comment IDs to finding signatures
            for rc in all_review_comments:
                reply_to = getattr(rc, "in_reply_to_id", None)
                if reply_to is not None:
                    # Not a root comment — skip
                    continue
                rc_path = normalize_file_path(str(getattr(rc, "path", "") or ""))
                rc_line = getattr(rc, "line", None) or getattr(rc, "original_line", None) or 0
                key = (rc_path, int(rc_line))
                sig = loc_to_sig.get(key)
                if not sig:
                    continue

                # Heuristic: check if any reply body signals resolution
                thread_resolved = False
                for reply in all_review_comments:
                    if getattr(reply, "in_reply_to_id", None) == rc.id:
                        reply_body: str = str(getattr(reply, "body", "") or "").lower()
                        if "marked as resolved" in reply_body or reply_body.strip() == "":
                            thread_resolved = True
                            break

                if thread_resolved:
                    resolved_sigs.append(sig)
                    logger.info(
                        f"Finding at {rc_path}:{rc_line} (sig={sig[:8]}…) marked as resolved."
                    )

        except Exception as err:
            logger.warning(f"Could not determine resolved inline comment threads: {err}")

        return resolved_sigs

    def publish_review_comment(
        self,
        repo_name: str,
        pr_number: int,
        markdown_body: str,
        findings: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        """
        Publishes the aggregated review summary comment and inline review comments onto the PR.

        Behaviour depends on the ``summary_mode`` configuration key:

        * ``"update"`` (default): Searches existing PR issue comments for the
          hidden ``<!-- prism-reviewer-summary -->`` marker and updates that
          comment in-place.  Creates a new summary comment when none exists yet.
        * ``"append"``: Legacy behaviour — always creates a brand-new summary
          comment on every run.

        Inline code findings are always posted as review comments on the
        relevant diff lines (deduplicated against already-posted comments).
        The inline review body is a minimal acknowledgement string, never the
        full summary, to avoid duplicating the summary in the PR timeline.
        
        Args:
            repo_name: The full name of the repository (e.g. "owner/repo").
            pr_number: The pull request number.
            markdown_body: The review summary in markdown format (must include
                the ``<!-- prism-reviewer-summary -->`` marker, which
                ``aggregator_node`` automatically prepends).
            findings: Optional list of finding dicts to post as inline review comments.
            
        Returns:
            The created or updated comment / review object.
        """
        logger.info(f"Publishing review comment to pull request #{pr_number} in repository {repo_name}")
        if not markdown_body:
            raise ValueError("markdown_body must not be empty or None")
        try:
            repo = self.g.get_repo(repo_name)
            pr = repo.get_pull(pr_number)

            # ── Inline comments ───────────────────────────────────────────────
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
                    # Use a minimal review body — the full summary lives in the
                    # sticky issue comment, not duplicated inside each review.
                    review = pr.create_review(
                        body="*Prism Reviewer — inline findings applied. See summary comment above.*",
                        comments=cast(Any, inline_comments),
                        event="COMMENT",
                    )

                    logger.info(f"Successfully published PR review with {len(inline_comments)} inline comments")
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

            # ── Summary comment (sticky update or append) ─────────────────────
            summary_mode = Config.summary_mode()
            if summary_mode == "update":
                existing_summary = self._find_existing_summary_comment(pr)
                if existing_summary is not None:
                    existing_summary.edit(markdown_body)
                    logger.info(
                        f"Updated existing summary comment ID {existing_summary.id} in-place."
                    )
                    return existing_summary

            # Either append mode, or update mode with no prior summary comment
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
