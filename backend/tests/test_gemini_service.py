"""Testes para a política de repetição da integração Gemini."""

from unittest.mock import Mock, call, patch

import pytest

from app.services.gemini_service import (
    _generate_content_with_retry,
)


class TransientGeminiError(Exception):
    code = 503


def test_generate_content_retries_503_then_succeeds():
    client = Mock()
    expected = Mock()
    client.models.generate_content.side_effect = [
        TransientGeminiError("temporarily unavailable"),
        TransientGeminiError("temporarily unavailable"),
        expected,
    ]

    with patch("app.services.gemini_service.time.sleep") as sleep:
        response = _generate_content_with_retry(
            client, model="gemini-test", contents="prompt", config=object()
        )

    assert response is expected
    assert client.models.generate_content.call_count == 3
    assert sleep.call_args_list == [call(1), call(2)]


def test_generate_content_does_not_retry_non_transient_error():
    client = Mock()
    client.models.generate_content.side_effect = ValueError("bad request")

    with patch("app.services.gemini_service.time.sleep") as sleep:
        with pytest.raises(ValueError, match="bad request"):
            _generate_content_with_retry(
                client, model="gemini-test", contents="prompt", config=object()
            )

    client.models.generate_content.assert_called_once()
    sleep.assert_not_called()


def test_generate_content_raises_after_retry_limit():
    client = Mock()
    client.models.generate_content.side_effect = TransientGeminiError("busy")

    with patch("app.services.gemini_service.time.sleep"):
        with pytest.raises(TransientGeminiError, match="busy"):
            _generate_content_with_retry(
                client, model="gemini-test", contents="prompt", config=object()
            )

    assert client.models.generate_content.call_count == 3
