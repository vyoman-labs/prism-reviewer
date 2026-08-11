"""
Unit tests for PR title and description resolution from GitHub API.
"""

import os
import json
from unittest.mock import patch, MagicMock

import pytest

from prism_reviewer.cli import _resolve_pr_api_details, main
from prism_reviewer.services.github import GitHubAppBridge


def test_fetch_pull_request_details_success():
    mock_g = MagicMock()
    mock_repo = MagicMock()
    mock_pr = MagicMock()
    mock_pr.title = "Fix database race condition"
    mock_pr.body = "Resolves issue with connection pool deadlocks."
    mock_pr.number = 42

    mock_g.get_repo.return_value = mock_repo
    mock_repo.get_pull.return_value = mock_pr

    bridge = GitHubAppBridge("fake-token")
    bridge.g = mock_g

    details = bridge.fetch_pull_request_details("owner/repo", 42)
    assert details["title"] == "Fix database race condition"
    assert details["description"] == "Resolves issue with connection pool deadlocks."
    assert details["number"] == 42


def test_resolve_pr_api_details_success(tmp_path):
    mock_logger = MagicMock()
    env = {
        "GITHUB_TOKEN": "test-token",
        "GITHUB_REPOSITORY": "test-owner/test-repo",
        "PR_NUMBER": "100",
    }
    with patch.dict(os.environ, env, clear=True):
        with patch("prism_reviewer.services.github.GitHubAppBridge.fetch_pull_request_details") as mock_fetch:
            mock_fetch.return_value = {
                "title": "API PR Title",
                "description": "API PR Description",
                "number": 100,
            }
            title, desc, pr_id = _resolve_pr_api_details(str(tmp_path), mock_logger)
            assert title == "API PR Title"
            assert desc == "API PR Description"
            assert pr_id == 100


def test_resolve_pr_api_details_missing_token(tmp_path):
    mock_logger = MagicMock()
    with patch.dict(os.environ, {}, clear=True):
        with patch("prism_reviewer.core.config.Config.github_token", return_value=None):
            title, desc, pr_id = _resolve_pr_api_details(str(tmp_path), mock_logger)
            assert title == ""
            assert desc == ""
            assert pr_id is None
            mock_logger.warning.assert_called_once()


def test_resolve_pr_api_details_github_ref_fallback(tmp_path):
    mock_logger = MagicMock()
    env = {
        "GITHUB_TOKEN": "test-token",
        "GITHUB_REPOSITORY": "test-owner/test-repo",
        "GITHUB_REF": "refs/pull/55/merge",
    }
    with patch.dict(os.environ, env, clear=True):
        with patch("prism_reviewer.services.github.GitHubAppBridge.fetch_pull_request_details") as mock_fetch:
            mock_fetch.return_value = {
                "title": "Ref PR Title",
                "description": "Ref PR Description",
                "number": 55,
            }
            title, desc, pr_id = _resolve_pr_api_details(str(tmp_path), mock_logger)
            assert title == "Ref PR Title"
            assert desc == "Ref PR Description"
            assert pr_id == 55


def test_resolve_pr_api_details_github_app_token(tmp_path):
    mock_logger = MagicMock()
    env = {
        "GITHUB_APP_TOKEN": "ghs_app_installation_token",
        "GITHUB_REPOSITORY": "test-owner/test-repo",
        "PR_NUMBER": "200",
    }
    with patch.dict(os.environ, env, clear=True):
        with patch("prism_reviewer.services.github.GitHubAppBridge.fetch_pull_request_details") as mock_fetch:
            mock_fetch.return_value = {
                "title": "App Token PR Title",
                "description": "App Token PR Description",
                "number": 200,
            }
            title, desc, pr_id = _resolve_pr_api_details(str(tmp_path), mock_logger)
            assert title == "App Token PR Title"
            assert desc == "App Token PR Description"
            assert pr_id == 200
            mock_logger.info.assert_any_call("Using GitHub App token (GITHUB_APP_TOKEN) to fetch PR details from GitHub API.")

