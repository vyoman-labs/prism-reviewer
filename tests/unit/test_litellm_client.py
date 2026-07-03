import pytest
from unittest.mock import MagicMock, patch
from prism_reviewer.integrations.litellm_client import ResilientLLMClient
from prism_reviewer.core.config import Config

@pytest.fixture
def mock_config():
    return {
        "llm": {
            "api_key": "some-key",
            "model": "some-model",
            "thresholds": {
                "max_requests_per_minute": 60,
                "max_concurrent_requests": 10,
                "retries": 2,
                "backoff_seconds": 1,
            }
        }
    }

def test_client_initialization(mock_config):
    client = ResilientLLMClient(mock_config)
    assert client.max_retries == 2
    assert client.backoff_factor == 1.0

@patch("prism_reviewer.integrations.litellm_client.litellm.completion")
@patch.object(Config, "llm_api_key", return_value="env-api-key")
@patch.object(Config, "llm_model_name", return_value="env-model-name")
def test_successful_completion(mock_model_name, mock_api_key, mock_completion, mock_config):
    # Setup mock response - severity is ADVISORY per rule
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"findings": ["issue1"]}'
    mock_response.choices = [mock_choice]
    mock_completion.return_value = mock_response

    client = ResilientLLMClient(mock_config)
    messages = [{"role": "user", "content": "hello"}]
    result = client.completion_with_retry(messages)

    assert result == '{"findings": ["issue1"]}'
    mock_completion.assert_called_once_with(
        model="env-model-name",
        messages=messages,
        api_key="env-api-key",
        response_format={"type": "json_object"},
        temperature=0.0,
        seed=1337
    )

@patch("prism_reviewer.integrations.litellm_client.litellm.completion")
@patch.object(Config, "llm_api_key", return_value="dummy-key")
@patch.object(Config, "llm_model_name", return_value="dummy-model")
@patch("prism_reviewer.integrations.litellm_client.time.sleep")
def test_retry_on_failure_then_success(mock_sleep, mock_model_name, mock_api_key, mock_completion, mock_config):
    # Fail once, then succeed
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"success": true}'
    mock_response.choices = [mock_choice]
    
    mock_completion.side_effect = [Exception("API Error"), mock_response]

    client = ResilientLLMClient(mock_config)
    result = client.completion_with_retry([])

    assert result == '{"success": true}'
    assert mock_completion.call_count == 2
    mock_sleep.assert_called_once_with(1.0) # backoff_factor (1.0) * 2^0 = 1.0

@patch("prism_reviewer.integrations.litellm_client.litellm.completion")
@patch.object(Config, "llm_api_key", return_value="dummy-key")
@patch.object(Config, "llm_model_name", return_value="dummy-model")
@patch("prism_reviewer.integrations.litellm_client.time.sleep")
def test_max_retries_returns_fallback(mock_sleep, mock_model_name, mock_api_key, mock_completion, mock_config):
    # Always fail
    mock_completion.side_effect = Exception("API Error")

    client = ResilientLLMClient(mock_config)
    result = client.completion_with_retry([])

    # Fallback string - severity ADVISORY per rule
    assert result == '{"findings": []}'
    # max_retries = 2, so 1 initial try + 2 retries = 3 calls total
    assert mock_completion.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1.0) # 1.0 * 2^0
    mock_sleep.assert_any_call(2.0) # 1.0 * 2^1
