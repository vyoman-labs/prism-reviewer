import os
import sys
from pathlib import Path
import pytest

# Ensure scripts directory is in sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root / "scripts" / "run_local"))

from run_local import parse_arguments


def test_run_local_parse_arguments_default_context_and_rules(monkeypatch):
    """Verifies parse_arguments accepts --repo and --pr and defaults optional flags."""
    test_args = ["run_local.py", "--repo", "owner/repo", "--pr", "42"]
    monkeypatch.setattr(sys, "argv", test_args)

    args = parse_arguments()
    assert args.repo == "owner/repo"
    assert args.pr == 42
    assert args.token is None
    assert args.output is None
    assert args.context is None
    assert args.rules is None


def test_run_local_parse_arguments_custom_context_and_rules(monkeypatch):
    """Verifies parse_arguments processes custom --context and --rules flags."""
    test_args = [
        "run_local.py",
        "--repo", "owner/repo",
        "--pr", "100",
        "--context", "custom_context.md",
        "--rules", "custom_rules.md"
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    args = parse_arguments()
    assert args.repo == "owner/repo"
    assert args.pr == 100
    assert args.context == "custom_context.md"
    assert args.rules == "custom_rules.md"
