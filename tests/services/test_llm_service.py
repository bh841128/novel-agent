from unittest.mock import MagicMock

from app.services.llm_service import LLMService


def _make_service():
    return LLMService(base_url="stub", api_key="x", model="test-model")


def test_stub_mode_does_not_create_client():
    svc = _make_service()
    assert svc._client is None
    assert svc._async_client is None


def test_generate_stream_yields_chunks():
    svc = _make_service()
    c1 = MagicMock()
    c1.choices = [MagicMock(delta=MagicMock(content="你"))]
    c2 = MagicMock()
    c2.choices = [MagicMock(delta=MagicMock(content="好"))]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = iter([c1, c2])
    svc._client = mock_client

    result = list(svc.generate_stream_sync([{"role": "user", "content": "hi"}]))
    assert result == ["你", "好"]


def test_generate_returns_full_text():
    svc = _make_service()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="你好世界"))]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    svc._client = mock_client

    result = svc.generate_sync([{"role": "user", "content": "hi"}])
    assert result == "你好世界"
