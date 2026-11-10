import json
import threading
from dataclasses import replace

import httpx
import pytest

from hovertranslate.core import (Cancelled, Rect, Settings, TextLine, UserError,
    capture_rect, choose_lines, endpoint, load_settings, popup_position,
    protect_secret, save_settings, stream_translation)


@pytest.mark.parametrize("screen", [Rect(0, 0, 1920, 1040), Rect(-1920, -200, 1920, 1080),
                                  Rect(1920, 0, 1280, 720)])
def test_popup_stays_in_work_area(screen):
    for x in [screen.x, screen.x+screen.width//2, screen.right-1]:
        for y in [screen.y, screen.y+screen.height//2, screen.bottom-1]:
            px, py = popup_position(x, y, 430, 330, screen)
            assert screen.x <= px and px+430 <= screen.right
            assert screen.y <= py and py+330 <= screen.bottom


def test_capture_clamps_to_monitor():
    monitor = Rect(-1280, 0, 1280, 720)
    assert capture_rect(-1280, 0, 900, 260, monitor) == Rect(-1280, 0, 900, 260)
    assert capture_rect(-1, 719, 900, 260, monitor) == Rect(-900, 460, 900, 260)


def sample_lines():
    return [TextLine("First line", Rect(20, 20, 200, 20), .95),
            TextLine("Second line", Rect(20, 50, 210, 20), .95),
            TextLine("Third line", Rect(20, 80, 190, 20), .95),
            TextLine("Other column", Rect(400, 50, 160, 20), .95)]


def test_line_and_whitespace_selection():
    assert choose_lines(sample_lines(), 80, 60, "line")[0] == "Second line"
    assert choose_lines(sample_lines(), 300, 210, "line") is None
    assert choose_lines([], 0, 0, "line") is None


def test_paragraph_does_not_cross_columns():
    lines = sample_lines()[:3]
    lines.append(TextLine("Other column", Rect(400, 150, 160, 20), .95))
    assert choose_lines(lines, 80, 60, "paragraph")[0] == "First line\nSecond line\nThird line"


def test_secret_is_encrypted_and_settings_roundtrip(tmp_path):
    key = "test-secret-never-a-real-api-key"
    protected = protect_secret(key)
    assert key not in protected
    assert protect_secret(protected, decrypt=True) == key
    path = tmp_path/"settings.json"
    settings = Settings(api_key=key)
    save_settings(settings, path)
    assert key not in path.read_text(encoding="utf-8")
    assert load_settings(path) == settings


@pytest.mark.parametrize("url", ["http://example.com/v1", "https://u:p@example.com",
                                 "https://example.com?key=secret", "file:///example", "bad"])
def test_invalid_endpoint(url):
    with pytest.raises(UserError):
        endpoint(url)


def test_endpoint_paths():
    assert endpoint("https://example.com/v1/") == "https://example.com/v1/chat/completions"
    assert endpoint("http://localhost:11434/v1/chat/completions").endswith("/v1/chat/completions")


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_streaming_unicode_auth_and_request():
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer example"
        body = json.loads(request.content)
        assert body["messages"][1]["content"] == "Hello"
        assert body["stream"] is True
        events = [json.dumps({"choices": [{"delta": {"content": chunk}}]}, ensure_ascii=False)
                  for chunk in ["你好", "，世界"]]
        stream = "\n\n".join("data: "+item for item in events)+"\n\ndata: [DONE]\n\n"
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=stream.encode())
    chunks = []
    with mock_client(handler) as client:
        result = stream_translation(Settings(base_url="https://example.com/v1", api_key="example"),
                                    "Hello", threading.Event(), chunks.append, client)
    assert result == "你好，世界"
    assert chunks == ["你好", "你好，世界"]


def test_non_streaming_compatible_response():
    with mock_client(lambda _: httpx.Response(200, json={"choices": [{"message": {"content": "你好"}}]})) as client:
        assert stream_translation(Settings(api_key="example"), "Hello", threading.Event(), lambda _: None, client) == "你好"


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 302])
def test_http_errors_hide_response_secrets(status):
    with mock_client(lambda _: httpx.Response(status, text="a provider might echo a secret")) as client:
        with pytest.raises(UserError) as error:
            stream_translation(Settings(api_key="example"), "Hello", threading.Event(), lambda _: None, client)
        assert "secret" not in str(error.value)


def test_cancel_before_request():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        stream_translation(Settings(api_key="example"), "Hello", cancel, lambda _: None)


def test_cancel_during_stream():
    cancel = threading.Event()
    event = 'data: {"choices":[{"delta":{"content":"test"}}]}\n\n'
    with mock_client(lambda _: httpx.Response(200, content=(event*3).encode())) as client:
        with pytest.raises(Cancelled):
            stream_translation(Settings(api_key="example"), "Hello", cancel, lambda _: cancel.set(), client)


def test_missing_key_is_actionable():
    with pytest.raises(UserError, match="API Key"):
        stream_translation(Settings(), "Hello", threading.Event(), lambda _: None)
