from typing import Any, Dict, List
import litellm

from ..core.logger import get_logger
from .events import BaseTokenObserver, TokenUsageEvent
from .observers import ConsoleLoggerObserver, JSONLFileObserver

logger = get_logger("prism_reviewer.monitoring.manager")


def patch_langfuse_version_compatibility() -> None:
    """
    Ensures compatibility between LiteLLM's Langfuse logger integration and different versions of the Langfuse SDK.
    LiteLLM attempts to access `langfuse.version.__version__`, whereas newer versions of Langfuse moved version
    metadata to `langfuse._version` or `langfuse.__version__`.
    """
    try:
        import sys
        lf = sys.modules.get("langfuse")
        if lf is None:
            try:
                import langfuse as lf  # type: ignore
            except ImportError:
                return

        if lf is not None and not hasattr(lf, "version"):
            if hasattr(lf, "_version"):
                setattr(lf, "version", getattr(lf, "_version"))
            else:
                import types
                _v_mod = types.ModuleType("version")
                setattr(_v_mod, "__version__", getattr(lf, "__version__", "1.0.0"))
                setattr(lf, "version", _v_mod)
    except Exception as e:
        logger.debug(f"Langfuse version compatibility patch skipped: {e}")


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
            if "langfuse" in callback_names:
                patch_langfuse_version_compatibility()

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
