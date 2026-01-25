import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from italki_anki.llm import OpenAIClient, parse_classified_items


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
