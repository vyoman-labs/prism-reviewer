import os
import re
import sys
from typing import Any, Dict

import tomllib

try:
    import dotenv  # type: ignore
except ImportError:
    dotenv = None  # type: ignore


class GlobalConfig:
    """
    A singleton configuration loader that reads TOML configuration files,
    substitutes environment variable placeholders, and casts numeric thresholds.
    """
    _instance = None
    _initialized = False

    # Matches environment variable placeholders.
    # Supports ${VAR} (no default) and ${VAR|-fallback} (with fallback).
    # Group 1: Environment variable name
    # Group 2: Fallback value (optional)
    PLACEHOLDER_PATTERN = re.compile(r"\${([A-Za-z0-9_]+)(?:\|-([^}]*))?}")

    def __new__(cls, *args, **kwargs):
        """Implements the singleton pattern to ensure only one configuration instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, file_path: str = "prism_reviewer.toml", env_file: str | None = None):
        """
        Initializes the configuration loader.
        
        Args:
            file_path: Path to the TOML configuration file. Defaults to 'prism_reviewer.toml'.
            env_file: Optional path to an environment variable file (.env).
        """
        if self._initialized:
            return
        
        self._data: Dict[str, Any] = self._load_and_process(file_path, env_file)
        self._initialized = True

    @classmethod
    def _load_dotenv(cls, env_file: str | None = None, is_custom_toml: bool = False) -> None:
        """
        Loads environment variables from .env / .env.local files into os.environ if not already defined.
        
        If env_file is provided, loads that specific file.
        If is_custom_toml is True and env_file is None, skips default .env loading for isolated test files.
        Otherwise, checks .env.local followed by .env, setting missing variables.
        
        Args:
            env_file: Explicit path to env file, or None to attempt loading default '.env.local' and '.env'.
            is_custom_toml: True if a non-default TOML path was passed (e.g. in test suites).
        """
        if env_file == "":
            return
        elif env_file:
            candidates = [env_file]
        elif is_custom_toml:
            return
        else:
            candidates = [".env.local", ".env"]

        for filepath in candidates:
            if os.path.exists(filepath):
                if dotenv is not None:
                    dotenv.load_dotenv(dotenv_path=filepath, override=False)
                else:
                    cls._parse_env_file(filepath)

    @classmethod
    def _parse_env_file(cls, filepath: str) -> None:
        """Fallback lightweight parser for .env files when python-dotenv is absent."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[7:].strip()
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
        except Exception:
            pass

    @classmethod
    def _substitute_env(cls, content: str) -> str:
        """
        Scans the configuration content and substitutes placeholders with environment variables.
        
        Args:
            content: Raw TOML content as a string.
            
        Returns:
            Processed TOML string with environment variables substituted.
        """
        def replacer(match: re.Match) -> str:
            env_var = match.group(1)
            # If a fallback value is specified after `|-`, use it. Otherwise, default to empty string.
            fallback = match.group(2) if match.group(2) is not None else ""
            return os.environ.get(env_var, fallback)
        
        return cls.PLACEHOLDER_PATTERN.sub(replacer, content)

    @classmethod
    def _sanitize_types(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitizes thresholds inside the [llm.thresholds] block to ensure they are integers.
        
        Args:
            data: Parsed configuration dictionary.
            
        Returns:
            Configuration dictionary with sanitized threshold types.
        """
        thresholds = data.get("llm", {}).get("thresholds", {})
        for key, value in thresholds.items():
            try:
                # Attempt to cast string placeholders/numbers to integers
                thresholds[key] = int(value)
            except (ValueError, TypeError):
                # Fallback to original value if casting fails
                pass
        return data

    def _load_and_process(self, file_path: str, env_file: str | None = None) -> Dict[str, Any]:
        """
        Loads the TOML file, processes environment variables, and parses it.
        
        Args:
            file_path: Absolute or relative path to the TOML config file.
            env_file: Optional path to an environment variable file (.env).
            
        Returns:
            A dictionary containing the parsed and processed configuration.
            
        Raises:
            FileNotFoundError: If the config file does not exist.
        """
        is_custom = os.path.basename(file_path) != "prism_reviewer.toml"
        self._load_dotenv(env_file, is_custom_toml=is_custom)

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Configuration file not found at: {file_path}")
            
        with open(file_path, "r", encoding="utf-8") as f:
            raw_content = f.read()

        # Substitute environment variables in raw TOML text before parsing
        processed_text = self._substitute_env(raw_content)
        # Parse processed TOML content
        parsed_toml = tomllib.loads(processed_text)
        # Ensure correct type constraints
        return self._sanitize_types(parsed_toml)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieves a configuration value by key with an optional default fallback."""
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        """Allows dictionary-like access to configuration keys (e.g., config['llm'])."""
        return self._data[key]

    def reset_for_testing(self, file_path: str = "prism_reviewer.toml", env_file: str | None = None):
        """
        Forces a reload of the configuration data. Primarily used in test suites.
        
        Args:
            file_path: Path to reload from. Defaults to 'prism_reviewer.toml'.
            env_file: Optional path to an environment variable file (.env).
        """
        self._data = self._load_and_process(file_path, env_file)

    def __repr__(self) -> str:
        """
        Returns a string representation of the configuration while masking sensitive
        credentials (LLM API key and GitHub token) to prevent leaking into log traces.
        """
        import copy
        safe_data = copy.deepcopy(self._data)
        
        # Safely extract and mask the api_key if present
        llm_block = safe_data.get("llm", {})
        if "api_key" in llm_block and isinstance(llm_block["api_key"], str):
            raw_key = llm_block["api_key"]
            if len(raw_key) > 8:
                # Mask intermediate characters, leaving the first 4 and last 4 exposed for verification
                llm_block["api_key"] = f"{raw_key[:4]}...{raw_key[-4:]}"
            elif raw_key:
                # Completely mask short keys
                llm_block["api_key"] = "********"

        # Safely extract and mask github token if present
        github_block = safe_data.get("github", {})
        if "token" in github_block and isinstance(github_block["token"], str):
            raw_token = github_block["token"]
            if len(raw_token) > 8:
                github_block["token"] = f"{raw_token[:4]}...{raw_token[-4:]}"
            elif raw_token:
                github_block["token"] = "********"
                
        return f"GlobalConfig({repr(safe_data)})"


class Config:
    """
    A class-level wrapper interface to the global configuration.
    Mainly used by cli.py and other parts of the system that expect Config class methods.
    """

    @classmethod
    def load(cls, file_path: str = "prism_reviewer.toml", env_file: str | None = None) -> None:
        """Loads/reloads configuration from the TOML file and optional .env file."""
        config.reset_for_testing(file_path=file_path, env_file=env_file)

    @classmethod
    def github_token(cls) -> str:
        """Returns the configured GitHub token."""
        github = config.get("github", {})
        return github.get("token", "")

    @classmethod
    def llm_model_name(cls) -> str:
        """Returns the configured LLM model name."""
        llm = config.get("llm", {})
        return llm.get("model", "")

    @classmethod
    def agent_model_name(cls, agent_name: str) -> str:
        """
        Returns the model name for a specific agent.
        
        If exactly one model config is set (either globally or for a specific agent),
        that model is used for all agents. Otherwise, each agent uses its own model config,
        falling back to the global LLM model.
        
        Args:
            agent_name: One of 'warden', 'architect', 'inspector', 'verifier'.
            
        Returns:
            The resolved model name for the agent, or 'gpt-4o' as a fallback.
        """
        global_model = cls.llm_model_name()
        
        agents_block = config.get("agents", {})
        models_block = agents_block.get("models", {}) if isinstance(agents_block, dict) else {}
        
        warden_model = models_block.get("warden", "") if isinstance(models_block, dict) else ""
        architect_model = models_block.get("architect", "") if isinstance(models_block, dict) else ""
        inspector_model = models_block.get("inspector", "") if isinstance(models_block, dict) else ""
        verifier_model = models_block.get("verifier", "") if isinstance(models_block, dict) else ""
        
        # Collect non-empty model names to check how many are configured
        configs = {
            "global": global_model,
            "warden": warden_model,
            "architect": architect_model,
            "inspector": inspector_model,
            "verifier": verifier_model,
        }
        
        non_empty_configs = {k: v for k, v in configs.items() if v}
        
        # If exactly one unique model configuration is set, use it for all agents
        unique_models = set(non_empty_configs.values())
        if len(unique_models) == 1:
            return next(iter(unique_models))
            
        # Otherwise, use the agent-specific config if set, falling back to global model
        specific_model = models_block.get(agent_name, "") if isinstance(models_block, dict) else ""
        if specific_model:
            return specific_model
            
        return global_model or "gpt-4o"

    @classmethod
    def llm_api_key(cls) -> str:
        """Returns the configured LLM provider API key."""
        llm = config.get("llm", {})
        return llm.get("api_key", "")

    @classmethod
    def llm_reasoning_effort(cls) -> str:
        """Returns the configured reasoning effort level (e.g. 'low', 'medium', 'high').

        Returns an empty string when the ``REASONING_EFFORT`` environment variable is
        not set, which instructs the LiteLLM client to omit the parameter entirely
        from the completion request.
        """
        llm = config.get("llm", {})
        return llm.get("reasoning_effort", "")


# --- Globally Exported Instance Variable ---
config = GlobalConfig()

