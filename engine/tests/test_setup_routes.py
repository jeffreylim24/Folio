import json

import httpx
import respx
from fastapi.testclient import TestClient
from keyring.errors import KeyringError

from folio_engine.config import Settings
from folio_engine.hardware import HardwareInfo
from folio_engine.secrets import SecretStore
from folio_engine.server import create_app

AUTH = {"Authorization": "Bearer secret"}


def test_hardware_route(tmp_path):
    fake = HardwareInfo("macos", "arm64", 24, True, None, 500)
    client = TestClient(create_app("secret", tmp_path, detect_hardware=lambda d: fake))
    r = client.get("/setup/hardware", headers=AUTH)
    body = r.json()
    assert r.status_code == 200
    assert body["recommended"] == "qwen3.5:9b-q4_K_M"
    assert body["reason"] == "ok"
    assert len(body["tiers"]) == 3
    assert body["device"]["usable_gb"] == 16.1


def test_put_model_rejects_uncatalogued(tmp_path):
    client = TestClient(create_app("secret", tmp_path))
    r = client.put("/setup/model", json={"model": "qwen3:14b"}, headers=AUTH)
    assert r.status_code == 400


def test_state_drops_uncatalogued_model(tmp_path):
    app = create_app("secret", tmp_path)
    app.state.config.save(Settings("ollama", "qwen3:14b", None, True))
    body = TestClient(app).get("/setup/state", headers=AUTH).json()
    assert body["settings"]["model"] is None
    assert body["settings"]["setup_complete"] is False
    saved = app.state.config.load()
    assert saved.model is None and saved.setup_complete is False


def test_state_keeps_catalog_model(tmp_path):
    app = create_app("secret", tmp_path)
    app.state.config.save(Settings("ollama", "qwen3.5:9b-q4_K_M", None, True))
    body = TestClient(app).get("/setup/state", headers=AUTH).json()
    assert body["settings"]["model"] == "qwen3.5:9b-q4_K_M"
    assert body["settings"]["setup_complete"] is True


def test_hardware_route_requires_token(tmp_path):
    client = TestClient(create_app("secret", tmp_path))
    assert client.get("/setup/hardware").status_code == 401


class FakeOllama:
    def __init__(self, versions):
        self._versions = versions

    def version(self):
        return self._versions.pop(0) if len(self._versions) > 1 else self._versions[0]


def test_ollama_status_route(tmp_path):
    client = TestClient(
        create_app("secret", tmp_path, ollama_client=FakeOllama(["0.9"]))
    )
    r = client.get("/setup/ollama", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["running"] is True
    assert r.json()["installed"] is True


def test_ollama_start_route_already_running(tmp_path):
    client = TestClient(
        create_app("secret", tmp_path, ollama_client=FakeOllama(["0.9"]))
    )
    r = client.post("/setup/ollama/start", headers=AUTH)
    assert r.json() == {"running": True}


def test_ollama_routes_require_token(tmp_path):
    client = TestClient(create_app("secret", tmp_path))
    assert client.get("/setup/ollama").status_code == 401
    assert client.post("/setup/ollama/start").status_code == 401


# --- API-key providers ---------------------------------------------------


OPENAI_MODELS = "https://api.openai.com/v1/models"
OPENAI_CHAT = "https://api.openai.com/v1/chat/completions"


class DictBackend:
    def __init__(self):
        self.data = {}

    def set_password(self, s, u, p):
        self.data[(s, u)] = p

    def get_password(self, s, u):
        return self.data.get((s, u))

    def delete_password(self, s, u):
        self.data.pop((s, u), None)


def api_client(tmp_path):
    secrets = SecretStore(DictBackend())
    app = create_app(
        "secret", tmp_path, secrets=secrets, ollama_client=FakeOllama(["0.9"])
    )
    return TestClient(app), secrets, app


def connect(client, key="sk-SECRET"):
    return client.post(
        "/setup/api-provider",
        headers=AUTH,
        json={"provider": "openai", "api_key": key},
    )


@respx.mock
def test_bad_key_not_saved(tmp_path):
    respx.get(OPENAI_MODELS).mock(return_value=httpx.Response(401))
    client, secrets, app = api_client(tmp_path)
    r = connect(client)
    assert r.status_code == 400
    assert r.json()["kind"] == "auth"
    assert secrets.get_api_key("openai") is None
    assert app.state.config.load().provider is None


@respx.mock
def test_network_error_kind(tmp_path):
    respx.get(OPENAI_MODELS).mock(side_effect=httpx.ConnectError("down"))
    client, _, _ = api_client(tmp_path)
    r = connect(client)
    assert r.status_code == 400
    assert r.json()["kind"] == "network"


@respx.mock
def test_good_key_saved(tmp_path):
    respx.get(OPENAI_MODELS).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
    )
    client, secrets, app = api_client(tmp_path)
    r = connect(client)
    assert r.status_code == 200
    assert r.json() == {"models": ["gpt-x"]}
    assert secrets.get_api_key("openai") == "sk-SECRET"
    s = app.state.config.load()
    assert s.provider == "openai" and s.setup_complete is False


@respx.mock
def test_api_key_never_in_settings_file(tmp_path):
    respx.get(OPENAI_MODELS).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
    )
    client, _, _ = api_client(tmp_path)
    connect(client)
    client.put("/setup/api-model", headers=AUTH, json={"model": "gpt-x"})
    assert "sk-SECRET" not in (tmp_path / "settings.json").read_text()


def test_api_provider_rejects_ollama_and_needs_base_url(tmp_path):
    client, _, _ = api_client(tmp_path)
    r = client.post(
        "/setup/api-provider", headers=AUTH, json={"provider": "ollama", "api_key": "k"}
    )
    assert r.status_code == 400
    r = client.post(
        "/setup/api-provider",
        headers=AUTH,
        json={"provider": "openai_compatible", "api_key": "k"},
    )
    assert r.status_code == 400


@respx.mock
def test_compatible_saves_base_url_but_others_ignore_it(tmp_path):
    respx.get("http://localhost:1234/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "m"}]})
    )
    respx.get(OPENAI_MODELS).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "m"}]})
    )
    client, _, app = api_client(tmp_path)
    r = client.post(
        "/setup/api-provider",
        headers=AUTH,
        json={
            "provider": "openai_compatible",
            "api_key": "k",
            "base_url": "http://localhost:1234/v1",
        },
    )
    assert r.status_code == 200
    assert app.state.config.load().base_url == "http://localhost:1234/v1"
    client.post(
        "/setup/api-provider",
        headers=AUTH,
        json={"provider": "openai", "api_key": "k", "base_url": "http://evil"},
    )
    assert app.state.config.load().base_url is None


@respx.mock
def test_test_prompt_completes_setup(tmp_path):
    respx.get(OPENAI_MODELS).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
    )
    route = respx.post(OPENAI_CHAT).mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "ready"}}]}
        )
    )
    client, _, app = api_client(tmp_path)
    connect(client)
    assert (
        client.put(
            "/setup/api-model", headers=AUTH, json={"model": "gpt-x"}
        ).status_code
        == 200
    )
    r = client.post("/setup/test", headers=AUTH)
    assert r.status_code == 200 and r.json() == {"reply": "ready"}
    assert json.loads(route.calls[0].request.content)["model"] == "gpt-x"
    assert app.state.config.load().setup_complete is True


@respx.mock
def test_test_failure_returns_kind(tmp_path):
    respx.get(OPENAI_MODELS).mock(return_value=httpx.Response(200, json={"data": []}))
    respx.post(OPENAI_CHAT).mock(return_value=httpx.Response(429))
    client, _, app = api_client(tmp_path)
    connect(client)
    client.put("/setup/api-model", headers=AUTH, json={"model": "gpt-x"})
    r = client.post("/setup/test", headers=AUTH)
    assert r.status_code == 400 and r.json()["kind"] == "rate_limit"
    assert app.state.config.load().setup_complete is False


def test_test_without_provider_is_400(tmp_path):
    client, _, _ = api_client(tmp_path)
    r = client.post("/setup/test", headers=AUTH)
    assert r.status_code == 400 and r.json()["kind"] == "other"


@respx.mock
def test_state_route(tmp_path):
    respx.get(OPENAI_MODELS).mock(return_value=httpx.Response(200, json={"data": []}))
    client, _, _ = api_client(tmp_path)
    body = client.get("/setup/state", headers=AUTH).json()
    assert body["has_api_key"] is False and body["settings"]["provider"] is None
    assert body["ollama"] is not None and "state" in body["pull"]
    connect(client)
    body = client.get("/setup/state", headers=AUTH).json()
    assert body["has_api_key"] is True
    assert body["ollama"] is None
    assert "sk-SECRET" not in json.dumps(body)


def test_new_routes_require_token(tmp_path):
    client, _, _ = api_client(tmp_path)
    assert client.get("/setup/state").status_code == 401
    assert client.post("/setup/test").status_code == 401
    assert client.put("/setup/api-model", json={"model": "x"}).status_code == 401


def test_validation_error_does_not_echo_request_body(tmp_path):
    client, _, _ = api_client(tmp_path)
    r = client.post("/setup/api-provider", headers=AUTH, json={"api_key": "sk-LEAK"})
    assert r.status_code == 422
    assert "sk-LEAK" not in r.text
    assert r.json() == {"kind": "other", "message": "Invalid request."}


# --- keychain failures ----------------------------------------------------


class FailingBackend:
    """A keychain that refuses every operation (e.g. access denied)."""

    def set_password(self, s, u, p):
        raise KeyringError("denied")

    def get_password(self, s, u):
        raise KeyringError("denied")

    def delete_password(self, s, u):
        raise KeyringError("denied")


def failing_client(tmp_path):
    app = create_app(
        "secret",
        tmp_path,
        secrets=SecretStore(FailingBackend()),
        ollama_client=FakeOllama(["0.9"]),
    )
    return TestClient(app), app


@respx.mock
def test_api_provider_keychain_failure_is_400(tmp_path):
    respx.get(OPENAI_MODELS).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
    )
    client, app = failing_client(tmp_path)
    r = connect(client)
    assert r.status_code == 400
    assert r.json() == {
        "kind": "other",
        "message": "Folio couldn't save your key to the system keychain. "
        "Check that you allowed access, then try again.",
    }
    assert app.state.config.load().provider is None


def test_state_keychain_failure_means_no_key(tmp_path):
    client, app = failing_client(tmp_path)
    app.state.config.save(Settings(provider="openai", model="gpt-x"))
    r = client.get("/setup/state", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["has_api_key"] is False


def test_test_keychain_failure_is_400(tmp_path):
    client, app = failing_client(tmp_path)
    app.state.config.save(Settings(provider="openai", model="gpt-x"))
    r = client.post("/setup/test", headers=AUTH)
    assert r.status_code == 400
    body = r.json()
    assert body["kind"] == "other"
    assert "keychain" in body["message"] and "denied" not in body["message"]
    assert app.state.config.load().setup_complete is False


# --- saving the "run privately" choice ------------------------------------


def test_put_provider_ollama_saves_choice(tmp_path):
    client, _, app = api_client(tmp_path)
    app.state.config.save(
        Settings(provider="openai", model="gpt-x", setup_complete=True)
    )
    r = client.put("/setup/provider", headers=AUTH, json={"provider": "ollama"})
    assert r.status_code == 200
    s = app.state.config.load()
    assert (s.provider, s.model, s.base_url, s.setup_complete) == (
        "ollama",
        None,
        None,
        False,
    )
    body = client.get("/setup/state", headers=AUTH).json()
    assert body["settings"]["provider"] == "ollama"


def test_put_provider_ollama_keeps_chosen_ollama_model(tmp_path):
    client, _, app = api_client(tmp_path)
    app.state.config.save(Settings(provider="ollama", model="qwen3.5:4b-q4_K_M"))
    client.put("/setup/provider", headers=AUTH, json={"provider": "ollama"})
    assert app.state.config.load().model == "qwen3.5:4b-q4_K_M"


def test_put_provider_rejects_api_providers_and_needs_token(tmp_path):
    client, _, _ = api_client(tmp_path)
    r = client.put("/setup/provider", headers=AUTH, json={"provider": "openai"})
    assert r.status_code == 422
    r = client.put("/setup/provider", json={"provider": "ollama"})
    assert r.status_code == 401


@respx.mock
def test_empty_reply_does_not_complete_setup(tmp_path):
    respx.get(OPENAI_MODELS).mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-x"}]})
    )
    respx.post(OPENAI_CHAT).mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": None}}]}
        )
    )
    client, _, app = api_client(tmp_path)
    connect(client)
    client.put("/setup/api-model", headers=AUTH, json={"model": "gpt-x"})
    r = client.post("/setup/test", headers=AUTH)
    assert r.status_code == 400 and r.json()["kind"] == "other"
    assert app.state.config.load().setup_complete is False
