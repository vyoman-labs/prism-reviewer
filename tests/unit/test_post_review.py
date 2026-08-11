"""Unit tests for scripts/post_review.py."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from scripts.post_review import publish_report_to_pr


class TestPostReview:
    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "fake-token",
            "GITHUB_REPOSITORY": "owner/repo",
            "PR_NUMBER": "42",
        },
        clear=True,
    )
    @patch("scripts.post_review.GitHubAppBridge")
    def test_publish_report_to_pr_loads_findings_and_publishes(
        self, mock_bridge_cls, tmp_path
    ) -> None:
        report_file = tmp_path / "prism_review_report.md"
        report_file.write_text("### Review Summary", encoding="utf-8")

        findings_file = tmp_path / "prism_review_findings.json"
        findings_data = [
            {
                "file": "src/app.py",
                "line": 15,
                "agent": "warden",
                "severity": "CRITICAL",
                "message": "Bug detected",
            }
        ]
        findings_file.write_text(json.dumps(findings_data), encoding="utf-8")

        mock_bridge = MagicMock()
        mock_bridge_cls.return_value = mock_bridge

        with patch.dict(
            os.environ,
            {
                "REPORT_FILE_PATH": str(report_file),
                "REPORT_FINDINGS_FILE_PATH": str(findings_file),
            },
        ):
            publish_report_to_pr()

        mock_bridge_cls.assert_called_once_with("fake-token")
        mock_bridge.publish_review_comment.assert_called_once_with(
            "owner/repo", 42, "### Review Summary", findings=findings_data
        )

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "fake-token",
            "GITHUB_REPOSITORY": "owner/repo",
            "PR_NUMBER": "42",
        },
        clear=True,
    )
    @patch("scripts.post_review.GitHubAppBridge")
    def test_publish_report_to_pr_without_findings_file(
        self, mock_bridge_cls, tmp_path
    ) -> None:
        report_file = tmp_path / "prism_review_report.md"
        report_file.write_text("### Review Summary", encoding="utf-8")

        mock_bridge = MagicMock()
        mock_bridge_cls.return_value = mock_bridge

        with patch.dict(
            os.environ,
            {
                "REPORT_FILE_PATH": str(report_file),
                "REPORT_FINDINGS_FILE_PATH": str(tmp_path / "nonexistent.json"),
            },
        ):
            publish_report_to_pr()

        mock_bridge.publish_review_comment.assert_called_once_with(
            "owner/repo", 42, "### Review Summary", findings=None
        )
