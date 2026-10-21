import json

import httpx
import pytest
import respx

from folio_engine.config import Settings
from folio_engine.providers import ProviderError, make_provider
from folio_engine.providers.ollama import OllamaProvider
from folio_engine.secrets import SecretStore

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}}
MSGS = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]


class DictBackend:
    def __init__(self):
        self.data = {}

    def set_password(self, s, u, p):
        self.data[(s, u)] = p

    def get_password(self, s, u):
        return self.data.get((s, u))

    def delete_password(self, s, u):
        self.data.pop((s, u), None)


def build(provider, model="m", base_url=None, key="KEY-123"):
    return make_provider(
        Settings(provider=provider, model=model, base_url=base_url),
        SecretStore(DictBackend()),
        api_key=key,
    )


@respx.mock
def test_openai_list_and_complete():
    respx.get("https://api.openai.com/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-a"}, {"id": "b"}]})
    )
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "{}"}}]}
        )
    )
    p = build("openai")
    assert p.list_models() == ["gpt-a", "b"]
    assert p.complete(MSGS, SCHEMA) == "{}"
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer KEY-123"
    body = json.loads(req.content)
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "out", "schema": SCHEMA, "strict": True},
    }
    assert body["model"] == "m"


@respx.mock
def test_openai_compatible_uses_base_url():
    respx.get("http://localhost:1234/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "x"}]})
    )
    p = build("openai_compatible", base_url="http://localhost:1234/v1/")
    assert p.list_models() == ["x"]


@respx.mock
def test_anthropic_list_and_complete():
    respx.get("https://api.anthropic.com/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "claude-x"}]})
    )
    route = respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "tool_use", "name": "out", "input": {"a": "b"}}]
            },
        )
    )
    p = build("anthropic")
    assert p.list_models() == ["claude-x"]
    assert json.loads(p.complete(MSGS, SCHEMA)) == {"a": "b"}
    req = route.calls[0].request
    assert req.headers["x-api-key"] == "KEY-123"
    assert req.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(req.content)
    assert body["max_tokens"] == 4096
    assert body["tool_choice"] == {"type": "tool", "name": "out"}
    assert body["tools"][0]["input_schema"] == SCHEMA
    assert body["system"] == "sys"
    assert body["messages"] == [{"role": "user", "content": "hi"}]


@respx.mock
def test_anthropic_plain_text():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200, json={"content": [{"type": "text", "text": "ready"}]}
        )
    )
    assert build("anthropic").complete(MSGS) == "ready"


@respx.mock
def test_gemini_list_filters_and_strips_prefix():
    respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-a",
                        "supportedGenerationMethods": ["generateContent"],
                    },
                    {
                        "name": "models/embed",
                        "supportedGenerationMethods": ["embedContent"],
                    },
                ]
            },
        )
    )
    assert build("gemini").list_models() == ["gemini-a"]


@respx.mock
def test_gemini_complete_with_schema():
    route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gem:generateContent"
    ).mock(
        return_value=httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}
        )
    )
    assert build("gemini", model="gem").complete(MSGS, SCHEMA) == "{}"
    req = route.calls[0].request
    assert req.headers["x-goog-api-key"] == "KEY-123"
    body = json.loads(req.content)
    assert body["generationConfig"] == {
        "responseMimeType": "application/json",
        "responseSchema": SCHEMA,
    }
    assert body["systemInstruction"] == {"parts": [{"text": "sys"}]}


@pytest.mark.parametrize(
    "provider,url",
    [
        ("openai", "https://api.openai.com/v1/models"),
        ("anthropic", "https://api.anthropic.com/v1/models"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/models"),
    ],
)
@respx.mock
def test_401_is_auth_and_never_leaks_key(provider, url):
    respx.get(url).mock(
        return_value=httpx.Response(401, json={"error": {"message": "bad KEY-123"}})
    )
    with pytest.raises(ProviderError) as ei:
        build(provider).list_models()
    assert ei.value.kind == "auth"
    assert "KEY-123" not in str(ei.value)
    assert "KEY-123" not in ei.value.message


@respx.mock
def test_status_and_network_mapping():
    url = "https://api.openai.com/v1/models"
    p = build("openai")
    respx.get(url).mock(return_value=httpx.Response(429))
    with pytest.raises(ProviderError) as ei:
        p.list_models()
    assert ei.value.kind == "rate_limit"
    respx.get(url).mock(
        return_value=httpx.Response(500, json={"error": {"message": "boom"}})
    )
    with pytest.raises(ProviderError) as ei:
        p.list_models()
    assert ei.value.kind == "other" and "boom" in ei.value.message
    respx.get(url).mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(ProviderError) as ei:
        p.list_models()
    assert ei.value.kind == "network"
    respx.get(url).mock(side_effect=httpx.ReadTimeout("x"))
    with pytest.raises(ProviderError) as ei:
        p.list_models()
    assert ei.value.kind == "network"


class FakeOllamaClient:
    def __init__(self, exc=None):
        self.exc = exc

    def list_models(self):
        if self.exc:
            raise self.exc
        return ["q"]

    def chat(self, model, messages, json_schema=None):
        if self.exc:
            raise self.exc
        return f"{model}:{json_schema}"


def test_ollama_provider_wraps_client():
    p = make_provider(
        Settings(provider="ollama", model="q"),
        SecretStore(DictBackend()),
        ollama_client=FakeOllamaClient(),
    )
    assert isinstance(p, OllamaProvider)
    assert p.list_models() == ["q"]
    assert p.complete(MSGS, SCHEMA) == f"q:{SCHEMA}"


def test_ollama_error_mapping():
    req = httpx.Request("POST", "http://x")
    status = httpx.HTTPStatusError(
        "x",
        request=req,
        response=httpx.Response(500, json={"error": "no model"}, request=req),
    )
    p = OllamaProvider(FakeOllamaClient(status), "q")
    with pytest.raises(ProviderError) as ei:
        p.complete(MSGS)
    assert ei.value.kind == "other" and "no model" in ei.value.message
    p = OllamaProvider(FakeOllamaClient(httpx.ConnectError("x")), "q")
    with pytest.raises(ProviderError) as ei:
        p.list_models()
    assert ei.value.kind == "network"


def test_missing_key_is_auth_error():
    with pytest.raises(ProviderError) as ei:
        make_provider(Settings(provider="openai"), SecretStore(DictBackend()))
    assert ei.value.kind == "auth"
