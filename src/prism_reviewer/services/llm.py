import time
from typing import Any, Dict, List

import litellm
from ..core.config import Config
from ..core.logger import get_logger

# Configure LiteLLM to drop unsupported parameters when calling standard models
litellm.drop_params = True

logger = get_logger("prism_reviewer.services.llm")


class ResilientLLMClient:
    """
    A bulletproof communication interface to talk to various model backends
    via LiteLLM using a single, unified key structure and exponential backoff retry.
    """

    def __init__(self, config_dict: dict):
        """
        Initializes the ResilientLLMClient with the parsed configuration dictionary.

        Args:
            config_dict: Parsed configuration dictionary.
        """
        self.config = config_dict
        thresholds = config_dict.get("llm", {}).get("thresholds", {})
        self.max_retries = int(thresholds.get("retries", 3))
        self.backoff_factor = float(thresholds.get("backoff_seconds", 2.0))

    def completion_with_retry(
        self,
        messages: List[Dict[str, Any]],
        reasoning_effort: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        Wraps litellm.completion with an exponential backoff retry loop.

        Reads ``api_key`` and ``model`` from the
        :class:`~prism_reviewer.core.config.Config` singleton (backed by
        ``prism_reviewer.toml`` and the corresponding environment variables:
        ``LLM_PROVIDER_API_KEY`` and ``LLM_MODEL_NAME``).

        The ``reasoning_effort`` parameter lets individual callers (e.g. agent
        nodes) override the global ``Config.llm_reasoning_effort()`` value on a
        per-call basis.  When ``None`` (the default), the global config value is
        used, preserving full backwards compatibility with existing callers.

        When the effective ``reasoning_effort`` is an empty string the parameter
        is omitted from the completion request so that standard (non-thinking)
        models are unaffected.

        Enforces strict JSON output, a deterministic seed, and 0.0 temperature.

        Args:
            messages: List of message dictionaries to send to the model.
            reasoning_effort: Optional per-call override for reasoning effort
                (e.g. ``"high"``, ``"medium"``, ``"low"``).  Overrides the
                global config value when provided.
            model: Optional model name to override the default global model configuration.

        Returns:
            The completion content as a string, or a fallback JSON string if all
            retries fail.
        """
        api_key = Config.llm_api_key()
        model_name = model if model is not None else (Config.llm_model_name() or "gpt-4o")
        # Resolve effective reasoning effort: default to empty string if not provided
        effective_effort = reasoning_effort or ""

        # Build optional extra kwargs so we never forward an empty/None value to
        # litellm, which could cause unexpected behaviour on standard models.
        extra_kwargs: dict = {}
        if effective_effort:
            extra_kwargs["reasoning_effort"] = effective_effort

        attempt = 0
        while True:
            try:
                logger.info(
                    f"Sending completion request to model={model_name} "
                    f"(attempt {attempt + 1}/{self.max_retries + 1})"
                    + (f", reasoning_effort={effective_effort}" if effective_effort else "")
                )
                response = litellm.completion(
                    model=model_name,
                    messages=messages,
                    api_key=api_key,
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    seed=1337,
                    **extra_kwargs,
                )
                choices = getattr(response, "choices", None)
                if choices:
                    content = choices[0].message.content
                    if content is not None:
                        return content
                raise ValueError("Received empty or invalid response from LiteLLM")
            except Exception as e:
                attempt += 1
                logger.warning(
                    f"LiteLLM call failed on attempt {attempt} with error: {e}"
                )
                if attempt > self.max_retries:
                    logger.error(
                        f"LiteLLM failed after {attempt} attempts. Returning safe fallback."
                    )
                    return '{"findings": []}'
                sleep_time = self.backoff_factor * (2 ** (attempt - 1))
                logger.info(f"Sleeping for {sleep_time:.2f} seconds before retrying...")
                time.sleep(sleep_time)
