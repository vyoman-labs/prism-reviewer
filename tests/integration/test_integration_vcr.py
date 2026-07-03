"""
Integration tests using vcrpy to capture and replay HTTP transactions with GitHub and OpenRouter.
"""

import os
from typing import Any, Dict, List, cast
from unittest.mock import patch

import pytest
import vcr
import litellm
import requests

from prism_reviewer.integrations.github import GitHubAppBridge
from prism_reviewer.integrations.litellm_client import ResilientLLMClient
from prism_reviewer.core.config import Config

# Dummy credentials used for replaying and testing in clean/CI environments
DUMMY_GITHUB_TOKEN: str = "DUMMY_GITHUB_TOKEN"
DUMMY_OPENROUTER_KEY: str = "DUMMY_OPENROUTER_KEY"

# Real credentials retrieved from the environment for recording cassettes
REAL_GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
REAL_OPENROUTER_KEY: str = os.environ.get("LLM_PROVIDER_API_KEY", "")


def before_record_request(request: Any) -> Any:
    """
    Scrubs sensitive keys and tokens from outgoing request headers and bodies before recording.

    Args:
        request: The VCR request object.

    Returns:
        The sanitized request object.
    """
    # Scrub Authorization headers (both case variants)
    for header in ["Authorization", "authorization"]:
        if header in request.headers:
            auth_header = request.headers[header]
            if REAL_OPENROUTER_KEY and REAL_OPENROUTER_KEY in auth_header:
                request.headers[header] = f"Bearer {DUMMY_OPENROUTER_KEY}"
            elif REAL_GITHUB_TOKEN and REAL_GITHUB_TOKEN in auth_header:
                request.headers[header] = f"token {DUMMY_GITHUB_TOKEN}"
            elif DUMMY_GITHUB_TOKEN in auth_header or DUMMY_OPENROUTER_KEY in auth_header:
                # If we are using dummy values, delete the header so public requests succeed
                del request.headers[header]
            else:
                request.headers[header] = f"Bearer {DUMMY_OPENROUTER_KEY}"

    # Scrub body content if it contains the real keys
    if request.body:
        body_str: str = ""
        is_bytes = isinstance(request.body, bytes)
        if is_bytes:
            try:
                body_str = request.body.decode("utf-8")
            except UnicodeDecodeError:
                pass
        else:
            body_str = str(request.body)

        if body_str:
            modified = False
            if REAL_OPENROUTER_KEY and REAL_OPENROUTER_KEY in body_str:
                body_str = body_str.replace(REAL_OPENROUTER_KEY, DUMMY_OPENROUTER_KEY)
                modified = True
            if REAL_GITHUB_TOKEN and REAL_GITHUB_TOKEN in body_str:
                body_str = body_str.replace(REAL_GITHUB_TOKEN, DUMMY_GITHUB_TOKEN)
                modified = True
            if modified:
                request.body = body_str.encode("utf-8") if is_bytes else body_str

    return request


def before_record_response(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scrubs sensitive or volatile information from incoming response headers and bodies before recording.

    Args:
        response: The VCR response dictionary.

    Returns:
        The sanitized response dictionary.
    """
    headers = response.get("headers", {})
    # Remove sensitive or highly volatile headers
    headers_to_remove: List[str] = [
        "Set-Cookie", "set-cookie", "Cookie", "cookie",
        "X-Github-Request-Id", "x-github-request-id",
        "X-Request-Id", "x-request-id",
        "Server", "server", "Date", "date"
    ]
    for h in headers_to_remove:
        if h in headers:
            headers[h] = ["REDACTED"]

    # Scrub body content if it contains the real keys
    body = response.get("body", {})
    if "string" in body:
        body_str: str = ""
        is_bytes = isinstance(body["string"], bytes)
        if is_bytes:
            try:
                body_str = body["string"].decode("utf-8")
            except UnicodeDecodeError:
                pass
        else:
            body_str = str(body["string"])

        if body_str:
            modified = False
            if REAL_OPENROUTER_KEY and REAL_OPENROUTER_KEY in body_str:
                body_str = body_str.replace(REAL_OPENROUTER_KEY, DUMMY_OPENROUTER_KEY)
                modified = True
            if REAL_GITHUB_TOKEN and REAL_GITHUB_TOKEN in body_str:
                body_str = body_str.replace(REAL_GITHUB_TOKEN, DUMMY_GITHUB_TOKEN)
                modified = True
            if modified:
                body["string"] = body_str.encode("utf-8") if is_bytes else body_str

    return response


# Determine record mode. Use type Any to avoid pyright mismatch with vcrpy internal RecordMode enums
RECORD_MODE: Any = "once" if (REAL_GITHUB_TOKEN and REAL_OPENROUTER_KEY) else "none"

integration_vcr = vcr.VCR(
    cassette_library_dir=os.path.join(os.path.dirname(__file__), "cassettes"),
    record_mode=RECORD_MODE,
    before_record_request=before_record_request,
    before_record_response=before_record_response,
    match_on=["method", "scheme", "host", "port", "path", "query"],
)


@pytest.mark.anyio
@patch.object(Config, "llm_api_key")
@patch.object(Config, "llm_model_name")
def test_litellm_client_integration(mock_model: Any, mock_key: Any) -> None:
    """
    Tests ResilientLLMClient completion utilizing vcrpy to mock OpenRouter completion.

    Args:
        mock_model: Mock for Config.llm_model_name.
        mock_key: Mock for Config.llm_api_key.
    """
    mock_key.return_value = REAL_OPENROUTER_KEY or DUMMY_OPENROUTER_KEY
    mock_model.return_value = "openrouter/google/gemini-2.5-flash"

    config_dict: Dict[str, Any] = {
        "llm": {
            "thresholds": {
                "retries": 1,
                "backoff_seconds": 1
            }
        }
    }
    client = ResilientLLMClient(config_dict)
    messages: List[Dict[str, str]] = [
        {"role": "user", "content": 'Respond with a simple JSON object containing {"hello": "world"}'}
    ]

    with integration_vcr.use_cassette("litellm_completion.yaml"):
        result = client.completion_with_retry(messages)

    assert result is not None
    assert "world" in result.lower()


@pytest.mark.anyio
@patch.object(Config, "llm_api_key")
def test_litellm_stream_integration(mock_key: Any) -> None:
    """
    Tests litellm.completion with stream=True using vcrpy to capture streaming chunks.

    Args:
        mock_key: Mock for Config.llm_api_key.
    """
    api_key = REAL_OPENROUTER_KEY or DUMMY_OPENROUTER_KEY
    mock_key.return_value = api_key

    messages: List[Dict[str, str]] = [
        {"role": "user", "content": "Respond with only the word Hello."}
    ]

    with integration_vcr.use_cassette("litellm_stream.yaml"):
        # Type annotated as Any to prevent pyright from raising attribute errors on choices delta
        response: Any = litellm.completion(
            model="openrouter/google/gemini-2.5-flash",
            messages=messages,
            api_key=api_key,
            stream=True,
            temperature=0.0
        )

        chunks: List[str] = []
        for chunk in response:
            content = chunk.choices[0].delta.content
            if content:
                chunks.append(content)

        full_text = "".join(chunks)

    assert len(full_text) > 0
    assert "hello" in full_text.lower()


@pytest.mark.anyio
def test_github_bridge_integration() -> None:
    """
    Tests GitHubAppBridge fetching PR diff, title, and description from GitHub PR endpoints.
    """
    token = REAL_GITHUB_TOKEN or DUMMY_GITHUB_TOKEN
    bridge = GitHubAppBridge(token)

    # Use a well-known public PR with a static diff for deterministic replay
    repo_name = "octocat/Spoon-Knife"
    pr_number = 40346  # A PR number that exists on octocat/Spoon-Knife

    # If we are using the dummy token, bypass token authentication for PyGithub
    if token == DUMMY_GITHUB_TOKEN:
        import github as PyGithub
        bridge.g = PyGithub.Github()

    # Intercept requests.get calls in the test to strip out the Authorization header if it is dummy
    original_get = requests.get

    def patched_get(*args: Any, **kwargs: Any) -> Any:
        if "headers" in kwargs and "Authorization" in kwargs["headers"]:
            auth = kwargs["headers"]["Authorization"]
            if DUMMY_GITHUB_TOKEN in auth or auth == "token ":
                del kwargs["headers"]["Authorization"]
        return original_get(*args, **kwargs)

    with patch("prism_reviewer.integrations.github.requests.get", side_effect=patched_get):
        with integration_vcr.use_cassette("github_pr_details.yaml"):
            title = bridge.fetch_pull_request_title(repo_name, pr_number)
            description = bridge.fetch_pull_request_description(repo_name, pr_number)
            diff = bridge.fetch_pull_request_diff(repo_name, pr_number)

    assert title is not None
    assert len(title) > 0
    assert isinstance(description, str)
    assert diff is not None
    assert len(diff) > 0
