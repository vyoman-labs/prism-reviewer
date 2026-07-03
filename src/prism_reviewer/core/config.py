import os
import re
import sys
from typing import Any, Dict

import tomllib


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

    def __init__(self, file_path: str = "prism_reviewer.toml"):
        """
        Initializes the configuration loader.
        
        Args:
            file_path: Path to the TOML configuration file. Defaults to 'prism_reviewer.toml'.
        """
        if self._initialized:
            return
        
        self._data: Dict[str, Any] = self._load_and_process(file_path)
        self._initialized = True

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

    def _load_and_process(self, file_path: str) -> Dict[str, Any]:
        """
        Loads the TOML file, processes environment variables, and parses it.
        
        Args:
            file_path: Absolute or relative path to the TOML config file.
            
        Returns:
            A dictionary containing the parsed and processed configuration.
            
        Raises:
            FileNotFoundError: If the config file does not exist.
        """
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

    def reset_for_testing(self, file_path: str = "prism_reviewer.toml"):
        """
        Forces a reload of the configuration data. Primarily used in test suites.
        
        Args:
            file_path: Path to reload from. Defaults to 'prism_reviewer.toml'.
        """
        self._data = self._load_and_process(file_path)

    def __repr__(self) -> str:
        """
        Returns a string representation of the configuration while masking the LLM API key
        to prevent sensitive credentials from leaking into log traces.
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
                
        return f"GlobalConfig({repr(safe_data)})"


class Config:
    """
    A class-level wrapper interface to the global configuration.
    Mainly used by cli.py and other parts of the system that expect Config class methods.
    """

    @classmethod
    def load(cls) -> None:
        """Loads/reloads configuration from the default 'prism_reviewer.toml' file."""
        config.reset_for_testing()

    @classmethod
    def llm_model_name(cls) -> str:
        """Returns the configured LLM model name."""
        llm = config.get("llm", {})
        return llm.get("model", "")

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
