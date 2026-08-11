import os
import pytest
from unittest.mock import MagicMock, patch
import requests

from prism_reviewer import __version__
from prism_reviewer.services.github import GitHubAppBridge

def test_github_app_bridge_init():
    # Test successful initialization
    bridge = GitHubAppBridge("fake-token")
    assert bridge.token == "fake-token"
    assert bridge.g is not None

    # Test initialization with empty token
    with pytest.raises(ValueError, match="github_token must not be empty or None"):
        GitHubAppBridge("")

    # Test initialization with None
    with pytest.raises(ValueError, match="github_token must not be empty or None"):
        GitHubAppBridge(None)  # type: ignore[arg-type]

@patch("prism_reviewer.services.github.Github")
@patch("prism_reviewer.services.github.requests.get")
def test_fetch_pull_request_diff_api_success(mock_requests_get, mock_github_class):
    # Mock PyGithub Github instance and objects
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    
    mock_pr = MagicMock()
    mock_pr.url = "https://api.github.com/repos/owner/repo/pulls/1"
    mock_repo.get_pull.return_value = mock_pr
    
    # Mock requests.get response
    mock_response = MagicMock()
    mock_response.text = "raw diff text"
    mock_requests_get.return_value = mock_response

    bridge = GitHubAppBridge("fake-token")
    diff = bridge.fetch_pull_request_diff("owner/repo", 1)

    assert diff == "raw diff text"
    mock_github_instance.get_repo.assert_called_once_with("owner/repo")
    mock_repo.get_pull.assert_called_once_with(1)
    
    # Check requests call
    mock_requests_get.assert_called_once_with(
        "https://api.github.com/repos/owner/repo/pulls/1",
        headers={
            "Authorization": "token fake-token",
            "Accept": "application/vnd.github.v3.diff",
        },
        timeout=30
    )

@patch("prism_reviewer.services.github.Github")
@patch("prism_reviewer.services.github.requests.get")
def test_fetch_pull_request_diff_fallback_success(mock_requests_get, mock_github_class):
    # Mock PyGithub Github instance and objects
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    
    mock_pr = MagicMock()
    mock_pr.url = "https://api.github.com/repos/owner/repo/pulls/1"
    mock_repo.get_pull.return_value = mock_pr
    
    # Mock requests.get raising exception to trigger fallback
    mock_requests_get.side_effect = Exception("API Error")
    
    # Mock files
    file1 = MagicMock()
    file1.filename = "file1.txt"
    file1.patch = "@@ -1 +1 @@\n-old\n+new"
    
    file2 = MagicMock()
    file2.filename = "file2.txt"
    file2.patch = None  # should be ignored
    
    mock_pr.get_files.return_value = [file1, file2]

    bridge = GitHubAppBridge("fake-token")
    diff = bridge.fetch_pull_request_diff("owner/repo", 1)

    expected_diff = (
        "diff --git a/file1.txt b/file1.txt\n"
        "index 0000000..0000000\n"
        "--- a/file1.txt\n"
        "+++ b/file1.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new"
    )
    assert diff == expected_diff

@patch("prism_reviewer.services.github.Github")
@patch("prism_reviewer.services.github.requests.get")
def test_fetch_pull_request_diff_failure(mock_requests_get, mock_github_class):
    # Mock PyGithub Github instance and objects
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    
    mock_pr = MagicMock()
    mock_pr.url = "https://api.github.com/repos/owner/repo/pulls/1"
    mock_repo.get_pull.return_value = mock_pr
    
    # Both direct request and get_files fail
    mock_requests_get.side_effect = Exception("API Error")
    mock_pr.get_files.side_effect = Exception("Files Error")

    bridge = GitHubAppBridge("fake-token")
    with pytest.raises(RuntimeError, match="Failed to fetch pull request diff"):
        bridge.fetch_pull_request_diff("owner/repo", 1)

@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_success(mock_github_class):
    # Mock PyGithub Github instance and objects
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    
    mock_comment = MagicMock()
    mock_comment.id = 12345
    mock_pr.create_issue_comment.return_value = mock_comment

    bridge = GitHubAppBridge("fake-token")
    comment = bridge.publish_review_comment("owner/repo", 1, "### Review Summary")

    assert comment == mock_comment
    mock_pr.create_issue_comment.assert_called_once_with("### Review Summary")

@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_empty_body(mock_github_class):
    bridge = GitHubAppBridge("fake-token")
    with pytest.raises(ValueError, match="markdown_body must not be empty or None"):
        bridge.publish_review_comment("owner/repo", 1, "")

    with pytest.raises(ValueError, match="markdown_body must not be empty or None"):
        bridge.publish_review_comment("owner/repo", 1, None)  # type: ignore[arg-type]

@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_api_failure(mock_github_class):
    # Mock PyGithub Github instance and objects
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_pr.create_issue_comment.side_effect = Exception("GitHub API Error")

    bridge = GitHubAppBridge("fake-token")
    with pytest.raises(RuntimeError, match="Failed to publish review comment"):
        bridge.publish_review_comment("owner/repo", 1, "### Review Summary")

@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_with_inline_findings_success(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_review = MagicMock()
    mock_pr.create_review.return_value = mock_review
    # No existing summary comment → will create a new issue comment
    mock_pr.get_issue_comments.return_value = []
    mock_summary_comment = MagicMock()
    mock_pr.create_issue_comment.return_value = mock_summary_comment

    findings = [
        {
            "file": "src/main.py",
            "line": 42,
            "agent": "warden",
            "severity": "CRITICAL",
            "message": "Potential buffer overflow.",
        }
    ]

    bridge = GitHubAppBridge("fake-token")
    res = bridge.publish_review_comment("owner/repo", 1, "### Review Summary", findings=findings)

    # The returned value is now the summary issue comment, not the review object
    assert res == mock_summary_comment
    mock_pr.create_review.assert_called_once()
    _, kwargs = mock_pr.create_review.call_args
    # Inline review body must be the minimal acknowledgement, not the full summary
    assert "### Review Summary" not in kwargs["body"]
    assert kwargs["event"] == "COMMENT"
    assert len(kwargs["comments"]) == 1
    assert kwargs["comments"][0]["path"] == "src/main.py"
    assert kwargs["comments"][0]["line"] == 42
    assert f"Prism Reviewer AI v{__version__}" in kwargs["comments"][0]["body"]


@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_inline_fallback_to_issue_comment(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_pr.create_review.side_effect = Exception("Invalid line position")
    mock_comment = MagicMock()
    mock_comment.id = 999
    mock_pr.create_issue_comment.return_value = mock_comment

    findings = [
        {
            "file": "src/main.py",
            "line": 999,
            "agent": "inspector",
            "severity": "ADVISORY",
            "message": "Out of range line.",
        }
    ]

    bridge = GitHubAppBridge("fake-token")
    res = bridge.publish_review_comment("owner/repo", 1, "### Review Summary", findings=findings)

    assert res == mock_comment
    mock_pr.create_issue_comment.assert_called_once_with("### Review Summary")


@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_path_normalization(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_review = MagicMock()
    mock_pr.create_review.return_value = mock_review

    findings = [
        {
            "file": ".\\a\\src\\main.py",
            "line": 10,
            "agent": "warden",
            "severity": "MAJOR",
            "message": "Path formatting check.",
        }
    ]

    bridge = GitHubAppBridge("fake-token")
    bridge.publish_review_comment("owner/repo", 1, "### Review Summary", findings=findings)

    _, kwargs = mock_pr.create_review.call_args
    assert kwargs["comments"][0]["path"] == "src/main.py"


@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_partial_inline_fallback(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr

    # Batch create_review fails, but single comment create_review succeeds
    mock_pr.create_review.side_effect = [Exception("Batch line failure"), MagicMock()]
    mock_comment = MagicMock()
    mock_pr.create_issue_comment.return_value = mock_comment

    findings = [
        {"file": "src/main.py", "line": 10, "agent": "warden", "severity": "MAJOR", "message": "Valid line"}
    ]

    bridge = GitHubAppBridge("fake-token")
    res = bridge.publish_review_comment("owner/repo", 1, "### Review Summary", findings=findings)

    assert res == mock_comment
    assert mock_pr.create_review.call_count == 2
    mock_pr.create_issue_comment.assert_called_once_with("### Review Summary")


@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_deduplicates_in_memory_inline_comments(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_review = MagicMock()
    mock_pr.create_review.return_value = mock_review
    mock_pr.get_review_comments.return_value = []

    findings = [
        {"file": "src/main.py", "line": 10, "agent": "warden", "severity": "MAJOR", "message": "Duplicate check"},
        {"file": "src/main.py", "line": 10, "agent": "warden", "severity": "MAJOR", "message": "Duplicate check"},
    ]

    bridge = GitHubAppBridge("fake-token")
    bridge.publish_review_comment("owner/repo", 1, "### Review Summary", findings=findings)

    mock_pr.create_review.assert_called_once()
    _, kwargs = mock_pr.create_review.call_args
    assert len(kwargs["comments"]) == 1


@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_skips_already_posted_comments(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_comment = MagicMock()
    mock_pr.create_issue_comment.return_value = mock_comment

    from prism_reviewer import __version__
    existing_comment = MagicMock()
    existing_comment.path = "src/main.py"
    existing_comment.line = 10
    existing_comment.body = f"👮 **Warden** (⚠️ MAJOR)\n\nAlready posted.\n\n---\n*Prism Reviewer AI v{__version__}*"
    mock_pr.get_review_comments.return_value = [existing_comment]

    findings = [
        {"file": "src/main.py", "line": 10, "agent": "warden", "severity": "MAJOR", "message": "Already posted."}
    ]

    bridge = GitHubAppBridge("fake-token")
    res = bridge.publish_review_comment("owner/repo", 1, "### Review Summary", findings=findings)

    assert res == mock_comment
    mock_pr.create_review.assert_not_called()
    mock_pr.create_issue_comment.assert_called_once_with("### Review Summary")


@patch("prism_reviewer.services.github.Github")
def test_fetch_pull_request_title_success(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_pr.title = "Test PR Title"
    mock_repo.get_pull.return_value = mock_pr

    bridge = GitHubAppBridge("fake-token")
    title = bridge.fetch_pull_request_title("owner/repo", 1)
    assert title == "Test PR Title"
    mock_github_instance.get_repo.assert_called_once_with("owner/repo")
    mock_repo.get_pull.assert_called_once_with(1)

@patch("prism_reviewer.services.github.Github")
def test_fetch_pull_request_title_failure(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_github_instance.get_repo.side_effect = Exception("API Error")

    bridge = GitHubAppBridge("fake-token")
    with pytest.raises(RuntimeError, match="Failed to fetch pull request title"):
        bridge.fetch_pull_request_title("owner/repo", 1)

@patch("prism_reviewer.services.github.Github")
def test_fetch_pull_request_description_success(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_pr.body = "Test PR Body Description"
    mock_repo.get_pull.return_value = mock_pr

    bridge = GitHubAppBridge("fake-token")
    description = bridge.fetch_pull_request_description("owner/repo", 1)
    assert description == "Test PR Body Description"

    # Test when body is None
    mock_pr.body = None
    description = bridge.fetch_pull_request_description("owner/repo", 1)
    assert description == ""

@patch("prism_reviewer.services.github.Github")
def test_fetch_pull_request_description_failure(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_github_instance.get_repo.side_effect = Exception("API Error")

    bridge = GitHubAppBridge("fake-token")
    with pytest.raises(RuntimeError, match="Failed to fetch pull request description"):
        bridge.fetch_pull_request_description("owner/repo", 1)

@patch("prism_reviewer.services.github.Github")
def test_fetch_pull_requests_by_date_success(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    
    mock_issue1 = MagicMock()
    mock_pr1 = MagicMock()
    mock_issue1.as_pull_request.return_value = mock_pr1
    
    mock_issue2 = MagicMock()
    # Mocking conversion failure on the second issue
    mock_issue2.as_pull_request.side_effect = Exception("Conversion Error")
    
    mock_github_instance.search_issues.return_value = [mock_issue1, mock_issue2]

    bridge = GitHubAppBridge("fake-token")
    pulls = bridge.fetch_pull_requests_by_date("owner/repo", "2023-01-01", "2023-01-31")
    
    assert len(pulls) == 2
    assert pulls[0] == mock_pr1
    assert pulls[1] == mock_issue2  # Fell back to the issue object itself
    
    mock_github_instance.search_issues.assert_called_once_with(
        query="is:pr repo:owner/repo created:2023-01-01..2023-01-31"
    )

@patch("prism_reviewer.services.github.Github")
def test_fetch_pull_requests_by_date_invalid_type(mock_github_class):
    bridge = GitHubAppBridge("fake-token")
    with pytest.raises(ValueError, match="date_type must be one of 'created', 'updated', 'merged'"):
        bridge.fetch_pull_requests_by_date("owner/repo", "2023-01-01", "2023-01-31", date_type="invalid")

@patch("prism_reviewer.services.github.Github")
def test_fetch_pull_requests_by_date_failure(mock_github_class):
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_github_instance.search_issues.side_effect = Exception("API error")

    bridge = GitHubAppBridge("fake-token")
    with pytest.raises(RuntimeError, match="Failed to fetch pull requests by date"):
        bridge.fetch_pull_requests_by_date("owner/repo", "2023-01-01", "2023-01-31")


def test_post_review_script_with_github_app_token(tmp_path):
    from scripts.post_review import publish_report_to_pr

    report_file = tmp_path / "prism_review_report.md"
    report_file.write_text("## PR Review Report\n\nLooks good!", encoding="utf-8")

    env = {
        "GITHUB_APP_TOKEN": "ghs_test_app_token",
        "GITHUB_REPOSITORY": "test-owner/test-repo",
        "PR_NUMBER": "42",
        "REPORT_FILE_PATH": str(report_file),
    }

    with patch.dict(os.environ, env, clear=True):
        with patch("scripts.post_review.GitHubAppBridge") as mock_bridge_cls:
            mock_bridge_inst = MagicMock()
            mock_bridge_cls.return_value = mock_bridge_inst

            publish_report_to_pr()

            mock_bridge_cls.assert_called_once_with("ghs_test_app_token")
            mock_bridge_inst.publish_review_comment.assert_called_once_with(
                "test-owner/test-repo", 42, "## PR Review Report\n\nLooks good!", findings=None
            )


# ── Sticky summary comment tests ─────────────────────────────────────────────

@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_update_mode_edits_existing_comment(mock_github_class):
    """In 'update' mode, publish_review_comment must edit the existing summary
    comment in-place when the prism-reviewer-summary marker is found."""
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_pr.get_review_comments.return_value = []

    # Existing issue comment that contains the hidden marker
    existing_comment = MagicMock()
    existing_comment.id = 999
    existing_comment.body = "<!-- prism-reviewer-summary -->\n# Old Report"
    mock_pr.get_issue_comments.return_value = [existing_comment]

    new_body = "<!-- prism-reviewer-summary -->\n# Updated Report"

    with patch("prism_reviewer.services.github.Config.summary_mode", return_value="update"):
        bridge = GitHubAppBridge("fake-token")
        result = bridge.publish_review_comment("owner/repo", 1, new_body)

    # Should have edited the existing comment, not created a new one
    existing_comment.edit.assert_called_once_with(new_body)
    mock_pr.create_issue_comment.assert_not_called()
    assert result is existing_comment


@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_update_mode_creates_when_no_existing(mock_github_class):
    """In 'update' mode, publish_review_comment must fall back to creating a
    new issue comment when no prior summary comment exists on the PR."""
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_pr.get_review_comments.return_value = []
    mock_pr.get_issue_comments.return_value = []  # No existing summary comment

    new_comment = MagicMock()
    new_comment.id = 1001
    mock_pr.create_issue_comment.return_value = new_comment

    new_body = "<!-- prism-reviewer-summary -->\n# First Report"

    with patch("prism_reviewer.services.github.Config.summary_mode", return_value="update"):
        bridge = GitHubAppBridge("fake-token")
        result = bridge.publish_review_comment("owner/repo", 1, new_body)

    mock_pr.create_issue_comment.assert_called_once_with(new_body)
    assert result is new_comment


@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_append_mode_always_creates(mock_github_class):
    """In 'append' mode, publish_review_comment must always create a new
    issue comment even when a prior summary comment exists."""
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_pr.get_review_comments.return_value = []

    # Even though an existing comment is present, append mode should ignore it
    existing_comment = MagicMock()
    existing_comment.body = "<!-- prism-reviewer-summary -->\n# Old Report"
    mock_pr.get_issue_comments.return_value = [existing_comment]

    new_comment = MagicMock()
    new_comment.id = 1002
    mock_pr.create_issue_comment.return_value = new_comment

    new_body = "<!-- prism-reviewer-summary -->\n# New Report"

    with patch("prism_reviewer.services.github.Config.summary_mode", return_value="append"):
        bridge = GitHubAppBridge("fake-token")
        result = bridge.publish_review_comment("owner/repo", 1, new_body)

    mock_pr.create_issue_comment.assert_called_once_with(new_body)
    existing_comment.edit.assert_not_called()
    assert result is new_comment


@patch("prism_reviewer.services.github.Github")
def test_publish_review_comment_inline_body_is_not_full_summary(mock_github_class):
    """The review body passed to pr.create_review must be a minimal
    acknowledgement string, not a copy of the full summary report."""
    mock_github_instance = MagicMock()
    mock_github_class.return_value = mock_github_instance
    mock_repo = MagicMock()
    mock_github_instance.get_repo.return_value = mock_repo
    mock_pr = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_review = MagicMock()
    mock_pr.create_review.return_value = mock_review
    mock_pr.get_review_comments.return_value = []
    mock_pr.get_issue_comments.return_value = []

    new_comment = MagicMock()
    mock_pr.create_issue_comment.return_value = new_comment

    findings = [
        {"file": "src/main.py", "line": 5, "agent": "warden", "severity": "MAJOR", "message": "Issue here"},
    ]
    summary_body = "<!-- prism-reviewer-summary -->\n# Report\n\n## ⚠️ MAJOR\n\nTable..."

    with patch("prism_reviewer.services.github.Config.summary_mode", return_value="update"):
        bridge = GitHubAppBridge("fake-token")
        bridge.publish_review_comment("owner/repo", 1, summary_body, findings=findings)

    # The review body should NOT be the full markdown_body
    _, kwargs = mock_pr.create_review.call_args
    review_body: str = kwargs.get("body", "")
    assert summary_body not in review_body
    assert "inline findings applied" in review_body.lower() or "prism reviewer" in review_body.lower()

