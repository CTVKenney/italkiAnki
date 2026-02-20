import io
import json
from unittest.mock import MagicMock, Mock, patch

import pytest
import urllib.error

from italki_anki.llm import (
    OpenAIClient,
    StubClient,
    build_openai_payload,
    chunk_lines,
    openai_client_from_env,
    parse_classified_items,
    post_json,
)


def test_parse_classified_items_with_envelope():
    payload = '{"items": [{"item_type": "vocabulary", "simplified": "书房", "traditional": "書房", "pinyin": "shūfáng", "english": "study"}]}'
    items = parse_classified_items(payload)
    assert len(items) == 1
    assert items[0].simplified == "书房"


def test_openai_client_parses_response():
    client = OpenAIClient(api_key="test-key", model="gpt-4o-mini")
    response_payload = {
        "choices": [
            {
                "message": {
                    "content": "{\"items\": [{\"item_type\": \"sentence\", \"simplified\": \"你好吗？\", \"traditional\": \"你好吗？\", \"pinyin\": \"nǐ hǎo ma\", \"english\": \"How are you?\"}]}"
                }
            }
        ]
    }
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.status = 200
    mock_response.read.return_value = json.dumps(response_payload).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_response) as mock_post:
        items = client.classify(["你好吗？"], seed=7)
        assert items[0].english == "How are you?"
        request = mock_post.call_args.args[0]
        assert b"\"seed\": 7" in request.data


def test_openai_client_rejects_bad_payload():
    client = OpenAIClient(api_key="test-key")
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.status = 200
    mock_response.read.return_value = b'{\"choices\": []}'
    with patch("urllib.request.urlopen", return_value=mock_response):
        with pytest.raises(ValueError):
            client.classify(["bad"])


def test_stub_client_classifies_lines():
    client = StubClient()
    items = client.classify(["清楚 = 明白", "你好吗？", "书房"])
    assert items[0].item_type.value == "grammar"
    assert items[1].item_type.value == "sentence"
    assert items[2].item_type.value == "vocabulary"


def test_stub_client_strips_parenthetical_gloss():
    client = StubClient()
    items = client.classify(["书房 (study)"])
    assert items[0].simplified == "书房"


def test_openai_payload_has_noise_and_measure_word_guardrails():
    payload = build_openai_payload(["面"], model="gpt-4o-mini", seed=None)
    system_prompt = payload["messages"][0]["content"]
    assert "social pleasantries" in system_prompt
    assert "include a common measure_word" in system_prompt


def test_post_json_retries_on_rate_limit(monkeypatch):
    payload = {"model": "gpt-4o-mini"}
    response_payload = {"choices": [{"message": {"content": "{\"items\": []}"}}]}
    response_body = json.dumps(response_payload).encode("utf-8")
    calls = {"count": 0}
    sleeps: list[float] = []

    def fake_urlopen(request, timeout=60):
        calls["count"] += 1
        if calls["count"] <= 2:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "rate limit",
                None,
                io.BytesIO(b"rate limited"),
            )
        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.status = 200
        mock_response.read.return_value = response_body
        return mock_response

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("random.random", lambda: 0.0)
    monkeypatch.setattr("time.sleep", lambda seconds: sleeps.append(seconds))

    result = post_json("https://api.openai.com/v1/chat/completions", payload, "key")

    assert result == response_payload
    assert calls["count"] == 3
    assert sleeps == [1, 2]


def test_post_json_429_after_retries_has_actionable_message(monkeypatch):
    payload = {"model": "gpt-4o-mini"}
    quota_body = (
        b'{"error":{"message":"You exceeded your current quota.","type":"insufficient_quota",'
        b'"code":"insufficient_quota"}}'
    )

    def fake_urlopen(request, timeout=60):
        raise urllib.error.HTTPError(
            request.full_url,
            429,
            "rate limit",
            None,
            io.BytesIO(quota_body),
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("random.random", lambda: 0.0)
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    with pytest.raises(RuntimeError) as exc_info:
        post_json("https://api.openai.com/v1/chat/completions", payload, "key")

    message = str(exc_info.value)
    assert "429" in message
    assert "insufficient quota" in message
    assert "insufficient_quota" in message


def test_openai_client_from_env_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        openai_client_from_env()


def test_openai_client_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENAI_MAX_LINES", "7")

    client = openai_client_from_env()

    assert client.api_key == "sk-test"
    assert client.model == "gpt-test"
    assert client.base_url == "https://example.test/v1"
    assert client.max_lines == 7


def test_post_json_non_retryable_http_error_surfaces_detail(monkeypatch):
    payload = {"model": "gpt-4o-mini"}
    body = b'{"error":{"message":"bad key","type":"invalid_request_error","code":"invalid_api_key"}}'

    def fake_urlopen(request, timeout=60):
        raise urllib.error.HTTPError(request.full_url, 401, "unauthorized", None, io.BytesIO(body))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as exc_info:
        post_json("https://api.openai.com/v1/chat/completions", payload, "bad-key")
    message = str(exc_info.value)
    assert "401" in message
    assert "invalid_api_key" in message


def test_post_json_urlerror_is_wrapped(monkeypatch):
    payload = {"model": "gpt-4o-mini"}

    def fake_urlopen(request, timeout=60):
        del request
        del timeout
        raise urllib.error.URLError("network down")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="network down"):
        post_json("https://api.openai.com/v1/chat/completions", payload, "key")


def test_chunk_lines_requires_positive_size():
    with pytest.raises(ValueError, match="chunk size must be positive"):
        list(chunk_lines(["a", "b"], 0))


def test_parse_classified_items_rejects_non_list_payload():
    with pytest.raises(ValueError, match="LLM response must be a list"):
        parse_classified_items('{"items":{"bad":"shape"}}')
