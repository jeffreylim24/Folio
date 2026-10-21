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
