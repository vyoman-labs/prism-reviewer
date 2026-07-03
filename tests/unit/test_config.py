import os
import pytest
from prism_reviewer.core.config import config, GlobalConfig

# Clean mock copy mirroring your exact file structure rules (using LLM_MODEL_OVERRIDE)
MOCK_TOML = """
[llm]
api_key = "${LLM_PROVIDER_API_KEY|-}"
model = "${LLM_MODEL_OVERRIDE|-gpt-4o}"

[llm.thresholds]
max_requests_per_minute = "${MAX_REQUESTS_PER_MINUTE|-60}"
max_concurrent_requests = "${MAX_CONCURRENT_REQUESTS|-10}"
retries = "${RETRIES|-3}"
backoff_seconds = "${BACKOFF_SECONDS|-2}"
"""

@pytest.fixture
def toml_file(tmp_path):
    """Generates a temporary configuration file inside an isolated sandbox."""
    file = tmp_path / "config.toml"
    file.write_text(MOCK_TOML, encoding="utf-8")
    return str(file)

@pytest.fixture(autouse=True)
def wipe_environment_leaks():
    """Ensures test-specific environment strings don't leak between assertion cycles."""
    targets = [
        "LLM_PROVIDER_API_KEY", "LLM_MODEL_OVERRIDE", 
        "MAX_REQUESTS_PER_MINUTE", "MAX_CONCURRENT_REQUESTS", 
        "RETRIES", "BACKOFF_SECONDS"
    ]
    for target in targets:
        os.environ.pop(target, None)
    yield


def test_singleton_memory_address_identity(toml_file):
    """Ensures creating secondary loaders points back to the initial instance memory stack."""
    instance_one = GlobalConfig(toml_file)
    instance_two = GlobalConfig(toml_file)
    assert instance_one is instance_two


def test_default_fallbacks_with_empty_environment(toml_file):
    """Validates fallback text values parse perfectly when environment is clear."""
    config.reset_for_testing(toml_file)
    
    assert config["llm"]["api_key"] == ""
    assert config["llm"]["model"] == "gpt-4o"
    
    # Assert type casting conversion mechanics function correctly
    thresholds = config["llm"]["thresholds"]
    assert thresholds["max_requests_per_minute"] == 60
    assert thresholds["max_concurrent_requests"] == 10
    assert thresholds["retries"] == 3
    assert thresholds["backoff_seconds"] == 2
    assert isinstance(thresholds["backoff_seconds"], int)


def test_environment_variables_actively_override_defaults(toml_file):
    """Confirms live exported variables correctly override default static fallbacks."""
    os.environ["LLM_PROVIDER_API_KEY"] = "live_token_abc123"
    os.environ["LLM_MODEL_OVERRIDE"] = "claude-3.5-sonnet"
    os.environ["BACKOFF_SECONDS"] = "12"
    
    config.reset_for_testing(toml_file)
    
    assert config["llm"]["api_key"] == "live_token_abc123"
    assert config["llm"]["model"] == "claude-3.5-sonnet"
    
    thresholds = config["llm"]["thresholds"]
    assert thresholds["backoff_seconds"] == 12
    assert thresholds["retries"] == 3  # Unset variable falls back correctly


def test_missing_file_throws_correct_exception():
    """Verifies loader yields a specific error message if config.toml vanishes."""
    with pytest.raises(FileNotFoundError):
        GlobalConfig()._load_and_process("non_existent_file.toml")

def test_config_logging_masks_api_key(toml_file):
    """Verifies that sensitive data fields are actively masked inside console representations."""
    os.environ["LLM_PROVIDER_API_KEY"] = "sk-live-secret-llm-token-string-value-12345"
    config.reset_for_testing(toml_file)
    
    # 1. Assert the raw values can still be read normally by your application code
    assert config["llm"]["api_key"] == "sk-live-secret-llm-token-string-value-12345"
    
    # 2. Assert printing or logging the object securely covers the key characters
    console_output = repr(config)
    assert "sk-live-secret-llm-token-string-value-12345" not in console_output
    assert "sk-l...2345" in console_output
