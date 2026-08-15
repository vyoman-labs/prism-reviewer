import json
import os
import threading
from typing import Callable

from ..core.logger import get_logger
from .events import BaseTokenObserver, TokenUsageEvent

logger = get_logger("prism_reviewer.monitoring.observers")


class ConsoleLoggerObserver(BaseTokenObserver):
    """
    Observer that outputs token usage metrics to standard prism-reviewer logger.
    """

    def on_token_usage(self, event: TokenUsageEvent) -> None:
        """
        Logs token consumption and request duration at INFO log level.

        Args:
            event: TokenUsageEvent containing LLM call usage data.
        """
        context_str = f" | Context: {event.caller_context}" if event.caller_context else ""
        logger.info(
            f"📊 LLM Token Usage [{event.model}] — "
            f"Prompt: {event.prompt_tokens}, "
            f"Completion: {event.completion_tokens}, "
            f"Total: {event.total_tokens} tokens | "
            f"Latency: {event.duration_seconds:.2f}s"
            f"{context_str}"
        )


class JSONLFileObserver(BaseTokenObserver):
    """
    Observer that writes token usage metrics as structured JSON Lines to a specified file.
    Uses a thread lock to ensure safe concurrent execution across async/multi-threaded nodes.
    """

    def __init__(self, file_path: str = ".prism_reviewer/token_usage.jsonl"):
        """
        Initializes the JSONL observer with a target output path.

        Args:
            file_path: Path to the .jsonl file where token events will be appended.
        """
        self.file_path = file_path
        self._lock = threading.Lock()

    def on_token_usage(self, event: TokenUsageEvent) -> None:
        """
        Appends the token usage event as a single JSON line to the target file.

        Args:
            event: TokenUsageEvent containing LLM call usage data.
        """
        payload = {
            "timestamp": event.timestamp,
            "model": event.model,
            "prompt_tokens": event.prompt_tokens,
            "completion_tokens": event.completion_tokens,
            "total_tokens": event.total_tokens,
            "duration_seconds": round(event.duration_seconds, 4),
            "reasoning_effort": event.reasoning_effort,
            "caller_context": event.caller_context,
        }
        try:
            line = json.dumps(payload) + "\n"
            dir_name = os.path.dirname(self.file_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with self._lock:
                with open(self.file_path, "a", encoding="utf-8") as f:
                    f.write(line)
        except Exception as e:
            logger.warning(f"Failed to write token usage event to JSONL file ({self.file_path}): {e}")


class CustomCallbackObserver(BaseTokenObserver):
    """
    Observer wrapping a user-supplied callable function for custom token tracking.
    """

    def __init__(self, callback: Callable[[TokenUsageEvent], None]):
        """
        Initializes the observer with a custom callback function.

        Args:
            callback: Callable accepting a TokenUsageEvent.
        """
        self.callback = callback

    def on_token_usage(self, event: TokenUsageEvent) -> None:
        """
        Executes the wrapped callback with the token usage event.

        Args:
            event: TokenUsageEvent containing LLM call usage data.
        """
        try:
            self.callback(event)
        except Exception as e:
            logger.warning(f"Custom token observer callback raised an exception: {e}")
