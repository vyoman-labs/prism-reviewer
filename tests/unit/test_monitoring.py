import json
import os
from unittest.mock import MagicMock, patch

import pytest
import litellm

from prism_reviewer.core.config import Config, GlobalConfig
from prism_reviewer.monitoring import (
    BaseTokenObserver,
    ConsoleLoggerObserver,
    CustomCallbackObserver,
    JSONLFileObserver,
    TokenUsageEvent,
    TokenUsageManager,
)
from prism_reviewer.services.llm import ResilientLLMClient


def test_token_usage_event_creation():
    event = TokenUsageEvent(
        model="gpt-4o",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        duration_seconds=1.23,
        reasoning_effort="high",
        caller_context={"agent": "warden", "region": 1},
    )
    assert event.model == "gpt-4o"
    assert event.prompt_tokens == 100
    assert event.completion_tokens == 50
    assert event.total_tokens == 150
    assert event.duration_seconds == 1.23
    assert event.reasoning_effort == "high"
    assert event.caller_context == {"agent": "warden", "region": 1}
    assert event.timestamp > 0


def test_console_logger_observer(caplog):
    observer = ConsoleLoggerObserver()
    event = TokenUsageEvent(
        model="claude-3-5-sonnet",
        prompt_tokens=200,
        completion_tokens=80,
        total_tokens=280,
        duration_seconds=0.45,
    )
    with caplog.at_level("INFO"):
        observer.on_token_usage(event)
    assert "LLM Token Usage [claude-3-5-sonnet]" in caplog.text
    assert "Prompt: 200" in caplog.text
    assert "Completion: 80" in caplog.text
    assert "Total: 280 tokens" in caplog.text


def test_jsonl_file_observer(tmp_path):
    log_file = tmp_path / "test_tokens.jsonl"
    observer = JSONLFileObserver(file_path=str(log_file))

    event1 = TokenUsageEvent(
        model="gemini-1.5-pro",
        prompt_tokens=500,
        completion_tokens=120,
        total_tokens=620,
        duration_seconds=2.1,
        reasoning_effort="medium",
        caller_context={"node": "architect"},
    )
    event2 = TokenUsageEvent(
        model="gemini-1.5-pro",
        prompt_tokens=300,
        completion_tokens=40,
        total_tokens=340,
        duration_seconds=0.8,
    )

    observer.on_token_usage(event1)
    observer.on_token_usage(event2)

    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    data1 = json.loads(lines[0])
    assert data1["model"] == "gemini-1.5-pro"
    assert data1["prompt_tokens"] == 500
    assert data1["completion_tokens"] == 120
    assert data1["total_tokens"] == 620
    assert data1["reasoning_effort"] == "medium"
    assert data1["caller_context"] == {"node": "architect"}

    data2 = json.loads(lines[1])
    assert data2["total_tokens"] == 340


def test_custom_callback_observer():
    captured_events = []

    def my_callback(evt: TokenUsageEvent):
        captured_events.append(evt)

    observer = CustomCallbackObserver(callback=my_callback)
    event = TokenUsageEvent(
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        duration_seconds=0.1,
    )

    observer.on_token_usage(event)
    assert len(captured_events) == 1
    assert captured_events[0].model == "gpt-4o-mini"


def test_token_usage_manager_dispatch():
    manager = TokenUsageManager()
    mock_obs1 = MagicMock(spec=BaseTokenObserver)
    mock_obs2 = MagicMock(spec=BaseTokenObserver)

    manager.register_observer(mock_obs1)
    manager.register_observer(mock_obs2)

    event = TokenUsageEvent(
        model="test-model",
        prompt_tokens=50,
        completion_tokens=20,
        total_tokens=70,
        duration_seconds=0.5,
    )

    manager.dispatch(event)
    mock_obs1.on_token_usage.assert_called_once_with(event)
    mock_obs2.on_token_usage.assert_called_once_with(event)

    manager.clear_observers()
    manager.dispatch(event)
    assert mock_obs1.on_token_usage.call_count == 1
    assert mock_obs2.on_token_usage.call_count == 1


def test_token_usage_manager_configure_from_config(tmp_path):
    manager = TokenUsageManager()
    log_file = tmp_path / "audit_tokens.jsonl"
    config_dict = {
        "monitoring": {
            "enabled": True,
            "observers": "console,jsonl",
            "jsonl_file_path": str(log_file),
            "litellm_callbacks": "langfuse,otel",
        }
    }

    # Reset litellm success/failure callbacks to clean state for testing
    litellm.success_callback = []
    litellm.failure_callback = []

    manager.configure_from_config(config_dict)

    assert len(manager._observers) == 2
    assert any(isinstance(o, ConsoleLoggerObserver) for o in manager._observers)
    assert any(isinstance(o, JSONLFileObserver) for o in manager._observers)

    assert "langfuse" in litellm.success_callback
    assert "otel" in litellm.success_callback
    assert "langfuse" in litellm.failure_callback
    assert "otel" in litellm.failure_callback


def test_config_monitoring_accessors(monkeypatch):
    monkeypatch.setenv("PRISM_MONITORING_ENABLED", "true")
    monkeypatch.setenv("PRISM_MONITORING_OBSERVERS", "console, jsonl")
    monkeypatch.setenv("PRISM_MONITORING_JSONL_PATH", ".prism_reviewer/test.jsonl")
    monkeypatch.setenv("PRISM_MONITORING_LITELLM_CALLBACKS", "langfuse, otel")

    GlobalConfig().reset_for_testing()

    assert Config.monitoring_enabled() is True
    assert Config.monitoring_observers() == ["console", "jsonl"]
    assert Config.monitoring_jsonl_path() == ".prism_reviewer/test.jsonl"
    assert Config.monitoring_litellm_callbacks() == ["langfuse", "otel"]


def test_resilient_llm_client_dispatches_token_event(monkeypatch):
    mock_observer = MagicMock(spec=BaseTokenObserver)
    
    client = ResilientLLMClient({
        "llm": {"model": "gpt-4o", "thresholds": {"retries": 1}},
        "monitoring": {"enabled": True, "observers": ""},
    })
    
    # Inject our mock observer into the singleton monitoring manager
    from prism_reviewer.monitoring import monitoring_manager
    monitoring_manager.clear_observers()
    monitoring_manager.register_observer(mock_observer)

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"status": "ok"}'))]
    mock_response.usage = MagicMock(prompt_tokens=120, completion_tokens=45, total_tokens=165)

    monkeypatch.setattr("litellm.completion", MagicMock(return_value=mock_response))

    messages = [{"role": "user", "content": "Hello"}]
    res = client.completion_with_retry(
        messages=messages,
        model="gpt-4o",
        caller_context={"agent": "warden"},
    )

    assert res == '{"status": "ok"}'
    mock_observer.on_token_usage.assert_called_once()
    event: TokenUsageEvent = mock_observer.on_token_usage.call_args[0][0]
    assert event.model == "gpt-4o"
    assert event.prompt_tokens == 120
    assert event.completion_tokens == 45
    assert event.total_tokens == 165
    assert event.caller_context == {"agent": "warden"}
