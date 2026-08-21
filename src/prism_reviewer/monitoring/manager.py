from typing import Any, Dict, List
import litellm

from ..core.logger import get_logger
from .events import BaseTokenObserver, TokenUsageEvent
from .observers import ConsoleLoggerObserver, JSONLFileObserver

logger = get_logger("prism_reviewer.monitoring.manager")


class TokenUsageManager:
    """
    Central manager for LLM token usage monitoring and observability integrations.
    Dispatches events to native observers and configures LiteLLM callbacks (e.g. Langfuse, OpenTelemetry).
    """

    def __init__(self) -> None:
        """Initializes an empty TokenUsageManager instance."""
        self._observers: List[BaseTokenObserver] = []
        self._configured: bool = False

    def register_observer(self, observer: BaseTokenObserver) -> None:
        """
        Registers a new native token observer.

        Args:
            observer: An instance implementing BaseTokenObserver.
        """
        if observer not in self._observers:
            self._observers.append(observer)

    def clear_observers(self) -> None:
        """Removes all registered native observers."""
        self._observers.clear()

    def dispatch(self, event: TokenUsageEvent) -> None:
        """
        Dispatches a TokenUsageEvent to all registered native observers.

        Args:
            event: TokenUsageEvent to publish.
        """
        for observer in self._observers:
            try:
                observer.on_token_usage(event)
            except Exception as e:
                logger.warning(f"Error in token observer {observer.__class__.__name__}: {e}")

    def configure_from_config(self, config_dict: Dict[str, Any]) -> None:
        """
        Configures observers and LiteLLM callbacks using the parsed prism-reviewer configuration.

        Args:
            config_dict: Parsed configuration dictionary.
        """
        monitoring_cfg = config_dict.get("monitoring", {})
        enabled = str(monitoring_cfg.get("enabled", "true")).lower() in ("true", "1", "yes")
        if not enabled:
            logger.info("LLM token usage monitoring is disabled in configuration.")
            return

        # 1. Configure Native Observers
        raw_observers = monitoring_cfg.get("observers", "console,jsonl")
        if isinstance(raw_observers, str):
            observer_names = [s.strip().lower() for s in raw_observers.split(",") if s.strip()]
        elif isinstance(raw_observers, list):
            observer_names = [str(s).strip().lower() for s in raw_observers if str(s).strip()]
        else:
            observer_names = ["console", "jsonl"]

        self.clear_observers()

        if "console" in observer_names:
            self.register_observer(ConsoleLoggerObserver())

        if "jsonl" in observer_names:
            jsonl_path = monitoring_cfg.get("jsonl_file_path", ".prism_reviewer/token_usage.jsonl")
            self.register_observer(JSONLFileObserver(file_path=jsonl_path))

        # 2. Configure LiteLLM Callbacks (e.g. Langfuse, OpenTelemetry)
        raw_callbacks = monitoring_cfg.get("litellm_callbacks", "")
        if isinstance(raw_callbacks, str):
            callback_names = [s.strip().lower() for s in raw_callbacks.split(",") if s.strip()]
        elif isinstance(raw_callbacks, list):
            callback_names = [str(s).strip().lower() for s in raw_callbacks if str(s).strip()]
        else:
            callback_names = []

        if callback_names:
            if not isinstance(litellm.success_callback, list):
                litellm.success_callback = []
            if not isinstance(litellm.failure_callback, list):
                litellm.failure_callback = []

            for cb in callback_names:
                if cb not in litellm.success_callback:
                    litellm.success_callback.append(cb)
                    logger.info(f"Registered LiteLLM success callback: {cb}")
                if cb not in litellm.failure_callback:
                    litellm.failure_callback.append(cb)
                    logger.info(f"Registered LiteLLM failure callback: {cb}")

        self._configured = True


# Globally accessible singleton instance
monitoring_manager = TokenUsageManager()
