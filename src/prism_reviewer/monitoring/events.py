from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
from typing import Any, Dict


@dataclass(frozen=True)
class TokenUsageEvent:
    """
    Represents an immutable event capturing LLM call token usage and execution metrics.

    Attributes:
        model: Name of the LLM model used for the completion request.
        prompt_tokens: Count of prompt (input) tokens.
        completion_tokens: Count of completion (output) tokens.
        total_tokens: Sum of prompt and completion tokens.
        duration_seconds: Wall-clock execution time of the LLM call in seconds.
        reasoning_effort: Thinking or reasoning effort configuration if set (e.g. 'high', 'medium', 'low').
        caller_context: Additional metadata passed by the caller (e.g. agent name, region index).
        timestamp: Epoch timestamp (seconds) when the call completed.
    """

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_seconds: float
    reasoning_effort: str = ""
    caller_context: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class BaseTokenObserver(ABC):
    """
    Abstract base class for all token usage observers in prism-reviewer.
    Custom observers should inherit from this class and implement `on_token_usage`.
    """

    @abstractmethod
    def on_token_usage(self, event: TokenUsageEvent) -> None:
        """
        Callback triggered when an LLM completion request finishes.

        Args:
            event: TokenUsageEvent containing token counts, model, duration, and context.
        """
        pass
