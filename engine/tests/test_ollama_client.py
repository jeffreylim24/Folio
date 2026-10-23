import httpx
import pytest
import respx

from folio_engine.config import ConfigStore
from folio_engine.ollama.client import OllamaClient, OllamaError, PullProgress
from folio_engine.pull import PullManager

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


@respx.mock
def test_pull_http_error_keeps_ollama_body_end_to_end(tmp_path):
    respx.post(f"{BASE}/api/pull").mock(
        return_value=httpx.Response(
            404, json={"error": "pull model manifest: file does not exist"}
        )
    )
    config = ConfigStore(tmp_path / "settings.json")
    mgr = PullManager(OllamaClient(BASE), config, lambda: 100)
    mgr.start("nope:1b", None)
    mgr.join(5)
    s = mgr.status()
    assert s.state == "error"
    assert "file does not exist" in s.error
    assert "internet" not in s.error


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("0.0.0.0", "http://127.0.0.1:11434"),
        ("0.0.0.0:11434", "http://127.0.0.1:11434"),
        ("localhost", "http://localhost:11434"),
        ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
        ("", "http://127.0.0.1:11434"),
        ("[::]:11434", "http://127.0.0.1:11434"),
        (":8080", "http://127.0.0.1:8080"),
        ("http://0.0.0.0:5000/", "http://127.0.0.1:5000"),
        ("example:1234", "http://example:1234"),
    ],
)
def test_ollama_host_is_normalised(monkeypatch, host, expected):
    monkeypatch.setenv("OLLAMA_HOST", host)
    assert OllamaClient()._base_url == expected


@respx.mock
def test_chat_sends_options_and_think():
    route = respx.post(f"{BASE}/api/chat").respond(json={"message": {"content": "hi"}})
    OllamaClient(BASE).chat("m", [], options={"num_ctx": 16384}, think=False)
    import json as _json

    body = _json.loads(route.calls[0].request.content)
    assert body["options"] == {"num_ctx": 16384}
    assert body["think"] is False


@respx.mock
def test_chat_omits_unset():
    route = respx.post(f"{BASE}/api/chat").respond(json={"message": {"content": "hi"}})
    OllamaClient(BASE).chat("m", [])
    import json as _json

    body = _json.loads(route.calls[0].request.content)
    assert "options" not in body and "think" not in body


def test_bad_ollama_host_port_falls_back(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert OllamaClient("http://localhost:abc")._base_url == "http://127.0.0.1:11434"
    monkeypatch.setenv("OLLAMA_HOST", "localhost:abc")
    assert OllamaClient()._base_url == "http://127.0.0.1:11434"
