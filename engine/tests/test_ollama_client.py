import httpx
import pytest
import respx

from folio_engine.ollama.client import OllamaClient, OllamaError, PullProgress

BASE = "http://127.0.0.1:11434"


@respx.mock
def test_version():
    respx.get(f"{BASE}/api/version").respond(json={"version": "0.9.1"})
    assert OllamaClient(BASE).version() == "0.9.1"


@respx.mock
def test_version_unreachable():
    respx.get(f"{BASE}/api/version").mock(side_effect=httpx.ConnectError("nope"))
    assert OllamaClient(BASE).version() is None


@respx.mock
def test_list_models():
    respx.get(f"{BASE}/api/tags").respond(json={"models": [{"name": "qwen3:14b"}]})
    assert OllamaClient(BASE).list_models() == ["qwen3:14b"]


@respx.mock
def test_pull_yields_progress():
    body = (
        '{"status":"pulling manifest"}\n'
        '{"status":"downloading","digest":"sha256:a","total":100,"completed":40}\n'
        '{"status":"success"}\n'
    )
    respx.post(f"{BASE}/api/pull").respond(content=body)
    got = list(OllamaClient(BASE).pull("qwen3:14b"))
    assert got == [
        PullProgress("pulling manifest", None, None, None),
        PullProgress("downloading", "sha256:a", 100, 40),
        PullProgress("success", None, None, None),
    ]


@respx.mock
def test_pull_error_line():
    respx.post(f"{BASE}/api/pull").respond(content='{"error":"boom"}\n')
    with pytest.raises(OllamaError, match="boom"):
        list(OllamaClient(BASE).pull("x"))


@respx.mock
def test_chat_sends_schema_and_returns_content():
    schema = {"type": "object"}
    route = respx.post(f"{BASE}/api/chat").respond(json={"message": {"content": "hi"}})
    out = OllamaClient(BASE).chat("m", [{"role": "user", "content": "yo"}], schema)
    assert out == "hi"
    import json

    sent = json.loads(route.calls.last.request.content)
    assert sent["format"] == schema
    assert sent["stream"] is False


def test_base_url_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://example:1234")
    assert OllamaClient()._base_url == "http://example:1234"
