import os
import pytest
from prism_reviewer.core.config import config, GlobalConfig, Config

# Clean mock copy mirroring your exact file structure rules (using LLM_MODEL)
MOCK_TOML = """
[llm]
api_key = "${LLM_PROVIDER_API_KEY|-}"
model = "${LLM_MODEL|-gpt-4o}"

[github]
token = "${GITHUB_TOKEN}"

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
        "GITHUB_TOKEN", "GITHUB_APP_TOKEN", "LLM_PROVIDER_API_KEY", "LLM_MODEL", 
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
    os.environ["LLM_MODEL"] = "claude-3.5-sonnet"
    os.environ["BACKOFF_SECONDS"] = "12"
    
    config.reset_for_testing(toml_file)
    
    assert config["llm"]["api_key"] == "live_token_abc123"
    assert config["llm"]["model"] == "claude-3.5-sonnet"


def test_missing_file_throws_correct_exception():
    """Verifies loader yields a specific error message if custom config file vanishes."""
    with pytest.raises(FileNotFoundError):
        GlobalConfig()._load_and_process("non_existent_file.toml")


def test_missing_default_config_file_uses_builtin_defaults(tmp_path, monkeypatch):
    """Verifies that missing prism_reviewer.toml falls back to built-in package defaults without error."""
    monkeypatch.chdir(tmp_path)
    config.reset_for_testing("prism_reviewer.toml")
    assert config["llm"]["thresholds"]["retries"] == 4
    assert config["llm"]["thresholds"]["max_requests_per_minute"] == 60
    assert config["agents"]["mode"] == "parallel"


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


def test_dotenv_file_loading_populates_placeholders(tmp_path):
    """Verifies that credentials and model supplied via a .env file populate config placeholders."""
    from prism_reviewer.core.config import Config

    env_file = tmp_path / ".env"
    env_file.write_text(
        "GITHUB_TOKEN=ghp_secret_token_123456789\n"
        "LLM_PROVIDER_API_KEY=sk-env-key-987654321\n"
        "LLM_MODEL=claude-3-5-sonnet\n",
        encoding="utf-8"
    )

    toml_content = """
    [github]
    token = "${GITHUB_TOKEN}"

    [llm]
    api_key = "${LLM_PROVIDER_API_KEY}"
    model = "${LLM_MODEL}"
    """
    toml_path = tmp_path / "prism_reviewer.toml"
    toml_path.write_text(toml_content, encoding="utf-8")

    # Wipe environment variables first to test .env loading
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("LLM_PROVIDER_API_KEY", None)
    os.environ.pop("LLM_MODEL", None)

    Config.load(file_path=str(toml_path), env_file=str(env_file))

    assert Config.github_token() == "ghp_secret_token_123456789"
    assert Config.llm_api_key() == "sk-env-key-987654321"
    assert Config.llm_model_name() == "claude-3-5-sonnet"

    console_output = repr(config)
    assert "ghp_secret_token_123456789" not in console_output
    assert "ghp_...6789" in console_output


def test_dotenv_local_precedence(tmp_path, monkeypatch):
    """Verifies that .env.local takes precedence over .env when both exist."""
    from prism_reviewer.core.config import Config

    monkeypatch.chdir(tmp_path)

    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=gpt-4o-env\n", encoding="utf-8")

    env_local = tmp_path / ".env.local"
    env_local.write_text("LLM_MODEL=gpt-4o-local\n", encoding="utf-8")

    toml_content = """
    [llm]
    api_key = "dummy"
    model = "${LLM_MODEL}"
    """
    toml_path = tmp_path / "prism_reviewer.toml"
    toml_path.write_text(toml_content, encoding="utf-8")

    os.environ.pop("LLM_MODEL", None)

    Config.load(file_path=str(toml_path))
    assert Config.llm_model_name() == "gpt-4o-local"


def test_github_app_token_environment_alias(toml_file):
    """Confirms setting GITHUB_APP_TOKEN populates token when GITHUB_TOKEN is not set."""
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ["GITHUB_APP_TOKEN"] = "ghs_app_token_9999"

    try:
        config.reset_for_testing(toml_file)
        assert Config.github_token() == "ghs_app_token_9999"
    finally:
        os.environ.pop("GITHUB_APP_TOKEN", None)
        config.reset_for_testing(toml_file)


def test_test_file_configs(tmp_path):
    """Verifies that configured [test_files] entries are appended on top of defaults."""
    toml_content = """
    [test_files]
    dirs = "e2e_tests, integration_tests"
    prefixes = "check_, verify_"
    suffixes = "_fixture, _e2e"
    exact = "setup_tests.py, test_harness.js"
    """
    toml_file = tmp_path / "prism_reviewer.toml"
    toml_file.write_text(toml_content, encoding="utf-8")

    config.reset_for_testing(str(toml_file))
    assert "tests" in Config.test_file_dirs()
    assert "e2e_tests" in Config.test_file_dirs()
    assert "integration_tests" in Config.test_file_dirs()

    assert "test_" in Config.test_file_prefixes()
    assert "check_" in Config.test_file_prefixes()
    assert "verify_" in Config.test_file_prefixes()

    assert "_test" in Config.test_file_suffixes()
    assert "_fixture" in Config.test_file_suffixes()
    assert "_e2e" in Config.test_file_suffixes()

    assert "conftest.py" in Config.test_file_exact()
    assert "setup_tests.py" in Config.test_file_exact()
    assert "test_harness.js" in Config.test_file_exact()
    config.reset_for_testing()



def test_test_file_default_configs():
    """Verifies default test file pattern lists on Config."""
    config.reset_for_testing()
    assert "tests" in Config.test_file_dirs()
    assert "test_" in Config.test_file_prefixes()
    assert "_test" in Config.test_file_suffixes()
    assert "conftest.py" in Config.test_file_exact()


def test_diff_mode_config(tmp_path):
    """Verifies that [git] diff_mode is loaded and defaults to 'auto'."""
    config.reset_for_testing()
    assert Config.diff_mode() == "auto"

    toml_content = """
    [git]
    diff_mode = "incremental"
    """
    toml_file = tmp_path / "prism_reviewer.toml"
    toml_file.write_text(toml_content, encoding="utf-8")
    config.reset_for_testing(str(toml_file))
    assert Config.diff_mode() == "incremental"
def test_previous_comments_config(tmp_path):
    """Verifies include_previous_comments and max_previous_comments config loading."""
    config.reset_for_testing()
    assert Config.include_previous_comments() is True
    assert Config.max_previous_comments() == 30

    toml_content = """
    [github]
    include_previous_comments = false
    max_previous_comments = 15
    """
    toml_file = tmp_path / "prism_reviewer.toml"
    toml_file.write_text(toml_content, encoding="utf-8")
    config.reset_for_testing(str(toml_file))
    assert Config.include_previous_comments() is False
    assert Config.max_previous_comments() == 15
    config.reset_for_testing()






