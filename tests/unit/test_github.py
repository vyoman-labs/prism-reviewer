import pytest
from unittest.mock import MagicMock, patch
import requests

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
