from fastapi.testclient import TestClient

from folio_engine.hardware import HardwareInfo
from folio_engine.server import create_app

AUTH = {"Authorization": "Bearer secret"}


def test_hardware_route(tmp_path):
    fake = HardwareInfo("macos", "arm64", 24, True, None, 500)
    client = TestClient(create_app("secret", tmp_path, detect_hardware=lambda d: fake))
    r = client.get("/setup/hardware", headers=AUTH)
    body = r.json()
    assert r.status_code == 200
    assert body["hardware"]["total_ram_gb"] == 24
    assert body["recommendation"]["model"]["name"] == "qwen3:14b"
    assert body["recommendation"]["reason"] == "ok"


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
