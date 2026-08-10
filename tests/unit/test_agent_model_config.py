"""
Tests for per-agent model configuration and fallback propagation logic using LLM_MODEL_OVERRIDE.
"""

import os
from pathlib import Path
from typing import Generator
import pytest
from prism_reviewer.core.config import Config, config


# Mock TOML structure for testing configuration loading (no LLM_MODEL_NAME)
TEST_MOCK_TOML = """
[llm]
api_key = "${LLM_PROVIDER_API_KEY|-}"
model = "${LLM_MODEL_OVERRIDE|-}"

[agents.models]
warden = "${WARDEN_MODEL_NAME|-}"
architect = "${ARCHITECT_MODEL_NAME|-}"
inspector = "${INSPECTOR_MODEL_NAME|-}"
verifier = "${VERIFIER_MODEL_NAME|-}"
"""

@pytest.fixture
def toml_file_path(tmp_path: Path) -> str:
    """Generates a temporary configuration file with agent model keys."""
    file = tmp_path / "prism_reviewer_test.toml"
    file.write_text(TEST_MOCK_TOML, encoding="utf-8")
    return str(file)

@pytest.fixture(autouse=True)
def clean_environment() -> Generator[None, None, None]:
    """Ensures test-specific environment strings don't leak between assertion cycles."""
    targets = [
        "LLM_PROVIDER_API_KEY",
        "LLM_MODEL_OVERRIDE",
        "WARDEN_MODEL_NAME",
        "ARCHITECT_MODEL_NAME",
        "INSPECTOR_MODEL_NAME",
        "VERIFIER_MODEL_NAME"
    ]
    # Remove from env
    for target in targets:
        os.environ.pop(target, None)
    yield
    # Cleanup after test finishes
    for target in targets:
        os.environ.pop(target, None)


def test_default_agent_model_no_fallback(toml_file_path: str) -> None:
    """Tests that when no model environment variables are set, no default fallback is used and empty string is returned."""
    config.reset_for_testing(toml_file_path)
    
    assert Config.agent_model_name("warden") == ""
    assert Config.agent_model_name("architect") == ""
    assert Config.agent_model_name("inspector") == ""
    assert Config.agent_model_name("verifier") == ""


def test_single_global_model_sets_all_agents(toml_file_path: str) -> None:
    """Tests that setting only LLM_MODEL_OVERRIDE configures all agents to use that model."""
    os.environ["LLM_MODEL_OVERRIDE"] = "claude-3-opus"
    config.reset_for_testing(toml_file_path)
    
    assert Config.agent_model_name("warden") == "claude-3-opus"
    assert Config.agent_model_name("architect") == "claude-3-opus"
    assert Config.agent_model_name("inspector") == "claude-3-opus"
    assert Config.agent_model_name("verifier") == "claude-3-opus"


def test_single_agent_model_sets_all_agents(toml_file_path: str) -> None:
    """Tests that when only one agent model config is set, it propagates to all agents."""
    os.environ["WARDEN_MODEL_NAME"] = "gemini-1.5-pro"
    config.reset_for_testing(toml_file_path)
    
    assert Config.agent_model_name("warden") == "gemini-1.5-pro"
    assert Config.agent_model_name("architect") == "gemini-1.5-pro"
    assert Config.agent_model_name("inspector") == "gemini-1.5-pro"
    assert Config.agent_model_name("verifier") == "gemini-1.5-pro"


def test_multiple_distinct_model_configs(toml_file_path: str) -> None:
    """Tests that if multiple model configs are set, agents use their respective overrides or fallback."""
    os.environ["LLM_MODEL_OVERRIDE"] = "global-model"
    os.environ["WARDEN_MODEL_NAME"] = "warden-model"
    os.environ["INSPECTOR_MODEL_NAME"] = "inspector-model"
    
    config.reset_for_testing(toml_file_path)
    
    # warden should use its override
    assert Config.agent_model_name("warden") == "warden-model"
    # inspector should use its override
    assert Config.agent_model_name("inspector") == "inspector-model"
    # architect should fallback to global (LLM_MODEL_OVERRIDE)
    assert Config.agent_model_name("architect") == "global-model"
    # verifier should fallback to global (LLM_MODEL_OVERRIDE)
    assert Config.agent_model_name("verifier") == "global-model"
