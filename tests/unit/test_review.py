import os
import pytest
import json
from unittest.mock import patch, MagicMock
from prism_reviewer.cli import main

@pytest.fixture
def clean_report(tmp_path):
    report_file = tmp_path / "prism_review_report.md"
    if report_file.exists():
        os.remove(report_file)
    yield report_file
    if report_file.exists():
        os.remove(report_file)

@patch("prism_reviewer.cli.Config")
@patch("prism_reviewer.cli.get_git_diff")
@patch("prism_reviewer.agents.nodes.ResilientLLMClient")
def test_cli_pr_review_with_custom_context_and_rules(mock_client_class, mock_git_diff, mock_config, tmp_path, clean_report):
    # Setup Config mocks
    mock_config.llm_model_name.return_value = "gpt-4o"
    mock_config.llm_api_key.return_value = "test-api-key"

    # Setup git diff mock with line 10 of src/main.py present
    mock_git_diff.return_value = (
        "diff --git a/src/main.py b/src/main.py\n"
        "@@ -1,15 +1,15 @@\n"
        " line 1\n"
        " line 2\n"
        " line 3\n"
        " line 4\n"
        " line 5\n"
        " line 6\n"
        " line 7\n"
        " line 8\n"
        " line 9\n"
        "+line 10: code to review\n"
        " line 11\n"
        " line 12\n"
        " line 13\n"
        " line 14\n"
        " line 15\n"
    )

    # Setup LLM client mock - severity is ADVISORY per rule
    mock_client = MagicMock()
    mock_client.completion_with_retry.return_value = json.dumps({
        "findings": [
            {
                "file": "src/main.py",
                "line": 10,
                "severity": "ADVISORY",
                "message": "Hardcoded API Key found!"
            }
        ]
    })
    mock_client_class.return_value = mock_client

    # Create dummy context and rules files
    context_file = tmp_path / "custom_context.md"
    context_file.write_text("My special project context", encoding="utf-8")

    rules_file = tmp_path / "custom_rules.md"
    rules_file.write_text("My custom review rules", encoding="utf-8")

    # Run cli main
    argv = [
        "--pr",
        "--repo", str(tmp_path),
        "--context", str(context_file),
        "--rules", str(rules_file)
    ]
    
    with patch("prism_reviewer.cli.config") as mock_global_config:
        mock_global_config._data = {}
        main(argv)

    # Check that report is generated
    assert clean_report.exists()
    report_content = clean_report.read_text(encoding="utf-8")
    assert "src/main.py" in report_content
    assert "ADVISORY" in report_content
    assert "Hardcoded API Key found!" in report_content

@patch("prism_reviewer.cli.Config")
@patch("prism_reviewer.cli.get_git_diff")
@patch("prism_reviewer.agents.nodes.ResilientLLMClient")
def test_cli_pr_review_defaults(mock_client_class, mock_git_diff, mock_config, tmp_path, clean_report):
    # Setup Config mocks
    mock_config.llm_model_name.return_value = "gpt-4o"
    mock_config.llm_api_key.return_value = "test-api-key"

    # Setup git diff mock
    # Need a valid diff format with line info so verifier doesn't drop findings if any are returned,
    # though here we return empty findings.
    mock_git_diff.return_value = "dummy diff content"

    # Setup LLM client mock
    mock_client = MagicMock()
    mock_client.completion_with_retry.return_value = json.dumps({
        "findings": []
    })
    mock_client_class.return_value = mock_client

    # Create default folder structure in temp directory
    prism_dir = tmp_path / ".prism_reviewer"
    prism_dir.mkdir()
    (prism_dir / "context.md").write_text("Default context content", encoding="utf-8")
    (prism_dir / "rules.md").write_text("Default rules content", encoding="utf-8")

    # Run cli main with default pathing
    argv = [
        "--pr",
        "--repo", str(tmp_path)
    ]
    
    with patch("prism_reviewer.cli.config") as mock_global_config:
        mock_global_config._data = {}
        main(argv)

    # Check that report is generated
    assert clean_report.exists()
    report_content = clean_report.read_text(encoding="utf-8")
    assert "No findings or issues identified." in report_content or "No findings" in report_content

@patch("prism_reviewer.cli.Config")
@patch("prism_reviewer.cli.get_git_diff")
@patch("prism_reviewer.agents.nodes.ResilientLLMClient")
def test_cli_pr_review_content_hashing_deduplication(mock_client_class, mock_git_diff, mock_config, tmp_path):
    # Setup Config mocks
    mock_config.llm_model_name.return_value = "gpt-4o"
    mock_config.llm_api_key.return_value = "test-api-key"
    
    # We need a proper diff format that maps to the line to review, so parse_diff_changed_lines allows it
    diff_content = (
        "diff --git a/src/main.py b/src/main.py\n"
        "@@ -1,3 +1,3 @@\n"
        " line 1\n"
        "+line 2: code to review\n"
        " line 3\n"
    )
    mock_git_diff.return_value = diff_content

    # Define path for test file
    test_file_rel = "src/main.py"
    test_file_abs = tmp_path / test_file_rel
    test_file_abs.parent.mkdir(parents=True, exist_ok=True)
    test_file_abs.write_text("line 1\nline 2: code to review\nline 3\n", encoding="utf-8")

    # Mock finding - severity must be ADVISORY per rule
    mock_client = MagicMock()
    mock_client.completion_with_retry.return_value = json.dumps({
        "findings": [
            {
                "file": test_file_rel,
                "line": 2,
                "severity": "ADVISORY",
                "message": "Bug at line 2!"
            }
        ]
    })
    mock_client_class.return_value = mock_client

    # First Run: Finding should be generated
    argv = ["--pr", "--repo", str(tmp_path)]
    with patch("prism_reviewer.cli.config") as mock_global_config:
        mock_global_config._data = {}
        main(argv)

    report_file = tmp_path / "prism_review_report.md"
    assert report_file.exists()
    report_content = report_file.read_text(encoding="utf-8")
    assert "Bug at line 2!" in report_content

    # Signatures file should exist
    sig_file = tmp_path / ".prism_reviewer" / "signatures.json"
    assert sig_file.exists()
    with open(sig_file, "r") as f:
        sigs = json.load(f)
    assert len(sigs) > 0

    # Second Run (identical content): Finding should be filtered out
    # Reset report file
    os.remove(report_file)
    with patch("prism_reviewer.cli.config") as mock_global_config:
        mock_global_config._data = {}
        main(argv)

    assert report_file.exists()
    report_content = report_file.read_text(encoding="utf-8")
    assert "No findings" in report_content or "No findings or issues identified." in report_content

    # Third Run (modified content around line 2): Finding should reappear
    # Change content of line 2 to change the diff context hash
    test_file_abs.write_text("line 1\nline 2: modified code\nline 3\n", encoding="utf-8")
    os.remove(report_file)
    with patch("prism_reviewer.cli.config") as mock_global_config:
        mock_global_config._data = {}
        main(argv)

    assert report_file.exists()
    report_content = report_file.read_text(encoding="utf-8")
    assert "Bug at line 2!" in report_content
