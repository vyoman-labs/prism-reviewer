import os
import threading
from typing import Any, Dict, List, Tuple, cast
import litellm
from litellm.integrations.custom_logger import CustomLogger

from ..core.logger import get_logger
from .events import BaseTokenObserver, TokenUsageEvent
from .observers import ConsoleLoggerObserver, JSONLFileObserver

logger = get_logger("prism_reviewer.monitoring.manager")


class ObservabilityStatusLogger(CustomLogger):
    """
    LiteLLM custom logger callback for explicit, real-time logging of telemetry metric publication.
    """

    def log_success_event(
        self, kwargs: Dict[str, Any], response_obj: Any, start_time: Any, end_time: Any
    ) -> None:
        """Logs successful publication of telemetry metrics for an LLM completion request."""
        model = str(kwargs.get("model", "unknown"))
        usage = getattr(response_obj, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        completion_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        total_tokens = getattr(usage, "total_tokens", 0) if usage else 0

        raw_cb = litellm.success_callback or []
        active_callbacks = [c for c in raw_cb if isinstance(c, str)]
        if active_callbacks:
            logger.info(
                f"LiteLLM telemetry metric published to callbacks ({', '.join(active_callbacks)}) for model={model} "
                f"(prompt_tokens={prompt_tokens}, completion_tokens={completion_tokens}, total_tokens={total_tokens})"
            )

    def log_failure_event(
        self, kwargs: Dict[str, Any], response_obj: Any, start_time: Any, end_time: Any
    ) -> None:
        """Logs failure when publishing telemetry metrics for an LLM completion request."""
        model = str(kwargs.get("model", "unknown"))
        exception = str(kwargs.get("exception", "Unknown error"))
        raw_cb = litellm.failure_callback or []
        active_callbacks = [c for c in raw_cb if isinstance(c, str)]
        if active_callbacks:
            logger.error(
                f"Failed to publish LiteLLM telemetry metric via callbacks ({', '.join(active_callbacks)}) for model={model}: {exception}"
            )


class TokenUsageManager:
    """
    Central manager for LLM token usage monitoring and observability integrations.
    Dispatches events to native observers and configures LiteLLM callbacks (e.g. Langfuse, OpenTelemetry).
    Accumulates overall PR token telemetry across LLM completion requests.
    """

    def __init__(self) -> None:
        """Initializes an empty TokenUsageManager instance with token accumulators."""
        self._observers: List[BaseTokenObserver] = []
        self._configured: bool = False
        self._active_callbacks: List[str] = []
        self._total_prompt_tokens: int = 0
        self._total_completion_tokens: int = 0
        self._total_tokens: int = 0
        self._request_count: int = 0
        self._lock: threading.Lock = threading.Lock()

    @property
    def total_prompt_tokens(self) -> int:
        """Returns the accumulated count of prompt (input) tokens."""
        with self._lock:
            return self._total_prompt_tokens

    @property
    def total_completion_tokens(self) -> int:
        """Returns the accumulated count of completion (output) tokens."""
        with self._lock:
            return self._total_completion_tokens

    @property
    def total_tokens(self) -> int:
        """Returns the accumulated total count of tokens."""
        with self._lock:
            return self._total_tokens

    @property
    def request_count(self) -> int:
        """Returns the accumulated count of LLM completion requests."""
        with self._lock:
            return self._request_count

    def reset_totals(self) -> None:
        """Resets accumulated PR token usage counters to zero."""
        with self._lock:
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._total_tokens = 0
            self._request_count = 0

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
        Dispatches a TokenUsageEvent to all registered native observers and accumulates totals.

        Args:
            event: TokenUsageEvent to publish.
        """
        with self._lock:
            self._total_prompt_tokens += event.prompt_tokens
            self._total_completion_tokens += event.completion_tokens
            self._total_tokens += event.total_tokens
            self._request_count += 1

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

        self._active_callbacks = callback_names

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

            # Register explicit observability status logger in litellm.callbacks
            if not isinstance(litellm.callbacks, list):
                litellm.callbacks = []
            if not any(isinstance(c, ObservabilityStatusLogger) for c in litellm.callbacks):
                litellm.callbacks.append(ObservabilityStatusLogger())

            if "langfuse" in callback_names:
                self._validate_langfuse_config()
            if "otel" in callback_names or "opentelemetry" in callback_names:
                self._validate_otel_config()

        self._configured = True

    def _validate_langfuse_config(self) -> None:
        """Validates Langfuse configuration and logs status or warnings."""
        pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        sk = os.getenv("LANGFUSE_SECRET_KEY", "")
        base_url = os.getenv("LANGFUSE_BASE_URL", "")
        host = os.getenv("LANGFUSE_HOST", "")

        if base_url and not host:
            os.environ["LANGFUSE_HOST"] = base_url
            host = base_url
            logger.info(f"Set LANGFUSE_HOST='{base_url}' from LANGFUSE_BASE_URL for Langfuse Python SDK v2 compatibility.")

        host = host or "https://cloud.langfuse.com"

        if not pk or not sk:
            logger.warning(
                "Langfuse callback is enabled in litellm_callbacks, but LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY "
                "environment variable is not set. Metrics will not be published to Langfuse server."
            )
        else:
            logger.info(f"Langfuse telemetry credentials configured successfully (host: {host}).")
            try:
                from litellm.integrations.langfuse.langfuse import LangFuseLogger
                lf_inst = LangFuseLogger(
                    langfuse_public_key=pk,
                    langfuse_secret=sk,
                    langfuse_host=host,
                )
                self._langfuse_logger_instance = lf_inst
                if not isinstance(litellm.callbacks, list):
                    litellm.callbacks = []
                if not any(isinstance(c, LangFuseLogger) for c in litellm.callbacks):
                    litellm.callbacks.append(cast(Any, lf_inst))

                # Non-blocking authentication verification (logs ERROR on 401 without failing step)
                client = getattr(lf_inst, "Langfuse", getattr(lf_inst, "langfuse", None))
                if client is not None and hasattr(client, "auth_check"):
                    try:
                        auth_res = client.auth_check()
                        if auth_res is False:
                            logger.error(f"Langfuse authentication check failed for host ({host}): Invalid API keys or project permissions.")
                    except Exception as auth_err:
                        logger.error(
                            f"Langfuse authentication failed for host ({host}): {auth_err}. "
                            "Telemetry traces will be dropped by Langfuse server. Verify LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST."
                        )
            except Exception as e:
                logger.warning(f"Could not pre-instantiate LangFuseLogger instance: {e}")

    def _validate_otel_config(self) -> None:
        """Validates OpenTelemetry configuration and logs status or warnings."""
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", ""))
        service_name = os.getenv("OTEL_SERVICE_NAME", "prism-reviewer")

        if not endpoint:
            logger.info(f"OpenTelemetry callback enabled (service: {service_name}, default endpoint).")
        else:
            logger.info(f"OpenTelemetry telemetry callback configured successfully (endpoint: {endpoint}, service: {service_name}).")

    def log_total_usage(self) -> Tuple[int, int, int, int]:
        """
        Logs the final accumulated PR token telemetry summary (input and output tokens).
        Automatically resets accumulated token counters afterwards.

        Returns:
            Tuple of (total_prompt_tokens, total_completion_tokens, total_tokens, request_count) prior to reset.
        """
        with self._lock:
            prompt_tokens = self._total_prompt_tokens
            completion_tokens = self._total_completion_tokens
            total_tokens = self._total_tokens
            req_count = self._request_count

        logger.info(
            f"📊 Final PR Token Telemetry Summary — "
            f"Input Tokens: {prompt_tokens}, "
            f"Output Tokens: {completion_tokens}, "
            f"Total Tokens: {total_tokens} "
            f"(across {req_count} LLM request{'s' if req_count != 1 else ''})"
        )

        self.reset_totals()
        return prompt_tokens, completion_tokens, total_tokens, req_count

    def flush_callbacks(self) -> None:
        """
        Logs final total PR token usage summary and flushes buffered telemetry queues
        for active LiteLLM callbacks (e.g. Langfuse, OpenTelemetry).
        """
        self.log_total_usage()

        if not self._configured:
            return

        if "langfuse" in self._active_callbacks:
            self._flush_langfuse_callbacks()
        if "otel" in self._active_callbacks or "opentelemetry" in self._active_callbacks:
            self._flush_otel_callbacks()

    def _flush_langfuse_callbacks(self) -> None:
        """Flushes the Langfuse telemetry queue and logs success or failure details."""
        pk = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        sk = os.getenv("LANGFUSE_SECRET_KEY", "")
        host = os.getenv("LANGFUSE_HOST", os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"))

        if not pk or not sk:
            logger.warning(
                f"Langfuse callback is enabled, but LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY is missing/empty. "
                f"Metrics were not published to Langfuse server ({host})."
            )
            return

        flushed_count = 0
        seen_clients: set[int] = set()

        try:
            # 1. Search LiteLLM's LangFuseHandler.langfuse_logger_map where LiteLLM stores active loggers
            try:
                from litellm.integrations.langfuse.langfuse_handler import LangFuseHandler
                logger_map = getattr(LangFuseHandler, "langfuse_logger_map", {})
                if isinstance(logger_map, dict):
                    for logger_obj in logger_map.values():
                        client = getattr(logger_obj, "Langfuse", getattr(logger_obj, "langfuse", None))
                        if client is not None and hasattr(client, "flush") and id(client) not in seen_clients:
                            client.flush()
                            seen_clients.add(id(client))
                            flushed_count += 1
            except Exception as e:
                logger.debug(f"Could not flush LangFuseHandler logger map: {e}")

            # 2. Check LiteLLM module-level langFuseLogger instance if set
            try:
                from litellm.litellm_core_utils import litellm_logging
                lfl = getattr(litellm_logging, "langFuseLogger", None)
                if lfl is not None:
                    client = getattr(lfl, "Langfuse", getattr(lfl, "langfuse", None))
                    if client is not None and hasattr(client, "flush") and id(client) not in seen_clients:
                        client.flush()
                        seen_clients.add(id(client))
                        flushed_count += 1
            except Exception as e:
                logger.debug(f"Could not flush module-level langFuseLogger: {e}")

            # 3. Check explicitly instantiated logger instance if set on manager
            if getattr(self, "_langfuse_logger_instance", None) is not None:
                lf_inst = self._langfuse_logger_instance
                client = getattr(lf_inst, "Langfuse", getattr(lf_inst, "langfuse", None))
                if client is not None and hasattr(client, "flush") and id(client) not in seen_clients:
                    client.flush()
                    seen_clients.add(id(client))
                    flushed_count += 1

            if flushed_count > 0:
                logger.info(f"Successfully published and flushed telemetry metrics for {flushed_count} active Langfuse client(s) to server ({host}).")
            else:
                logger.warning(f"Langfuse telemetry flush executed, but no active Langfuse client instances with telemetry events were found for host ({host}).")

        except Exception as e:
            logger.error(f"Failed to flush telemetry metrics to Langfuse server ({host}): {e}")

    def _flush_otel_callbacks(self) -> None:
        """Flushes OpenTelemetry spans queue and logs status."""
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "default"))
        try:
            import opentelemetry.trace as trace_api
            provider = trace_api.get_tracer_provider()
            flush_fn = getattr(provider, "force_flush", None)
            if callable(flush_fn):
                flush_fn()
                logger.info(f"Successfully published and flushed OpenTelemetry traces to OTLP collector ({endpoint}).")
            else:
                logger.info(f"OpenTelemetry telemetry flush completed ({endpoint}).")
        except Exception as e:
            logger.error(f"Failed to flush OpenTelemetry traces to OTLP collector ({endpoint}): {e}")


# Globally accessible singleton instance
monitoring_manager = TokenUsageManager()

