"""Tests for the reasoning_effort override in ResilientLLMClient."""

from unittest.mock import MagicMock, patch
import pytest

from prism_reviewer.core.config import Config, config
from prism_reviewer.integrations.litellm_client import ResilientLLMClient


@pytest.fixture(autouse=True)
def mock_config():
    """Ensures Config settings are mocked clean for each test."""
    with patch.object(Config, "llm_api_key", return_value="fake_key"), \
         patch.object(Config, "llm_model_name", return_value="fake-model"):
        yield


class TestResilientLLMClientReasoningOverride:
    @patch("prism_reviewer.integrations.litellm_client.litellm.completion")
    def test_completion_omits_parameter_when_none(self, mock_completion) -> None:
        """When reasoning_effort=None, the parameter is omitted from the call."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"findings": []}'))
        ]
        mock_completion.return_value = mock_response

        client = ResilientLLMClient(config._data)
        messages = [{"role": "user", "content": "test"}]
        
        client.completion_with_retry(messages, reasoning_effort=None)
        
        # Verify litellm.completion call parameters
        assert mock_completion.call_count == 1
        kwargs = mock_completion.call_args[1]
        assert "reasoning_effort" not in kwargs

    @patch("prism_reviewer.integrations.litellm_client.litellm.completion")
    def test_completion_uses_override_when_provided(self, mock_completion) -> None:
        """When reasoning_effort is explicitly overridden, that value must be passed to litellm."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"findings": []}'))
        ]
        mock_completion.return_value = mock_response

        client = ResilientLLMClient(config._data)
        messages = [{"role": "user", "content": "test"}]
        
        client.completion_with_retry(messages, reasoning_effort="high")
        
        assert mock_completion.call_count == 1
        kwargs = mock_completion.call_args[1]
        assert kwargs.get("reasoning_effort") == "high"

    @patch("prism_reviewer.integrations.litellm_client.litellm.completion")
    def test_completion_omits_parameter_when_empty_string(self, mock_completion) -> None:
        """When the resolved reasoning effort is an empty string, reasoning_effort should not be passed to litellm."""
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"findings": []}'))
        ]
        mock_completion.return_value = mock_response

        client = ResilientLLMClient(config._data)
        messages = [{"role": "user", "content": "test"}]
        
        # Override to empty string (e.g., standard non-thinking model)
        client.completion_with_retry(messages, reasoning_effort="")
        
        assert mock_completion.call_count == 1
        kwargs = mock_completion.call_args[1]
        assert "reasoning_effort" not in kwargs
