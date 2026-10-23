from fastapi.testclient import TestClient

from folio_engine.server import create_app


def test_health_requires_token(tmp_path):
    client = TestClient(create_app("secret", tmp_path))
    assert client.get("/health").status_code == 401
    assert (
        client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )


def test_health_ok(tmp_path):
    client = TestClient(create_app("secret", tmp_path))
    r = client.get("/health", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 200 and r.json()["ok"] is True


def test_cors_allows_tauri_origins(tmp_path):
    client = TestClient(create_app("secret", tmp_path))
    for origin in [
        "tauri://localhost",
        "http://tauri.localhost",
        "http://localhost:1420",
    ]:
        r = client.options(
            "/health",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )
        assert r.headers["access-control-allow-origin"] == origin


def test_state_and_overrides(tmp_path):
    fake = object()
    app = create_app("secret", tmp_path, config=fake)
    assert app.state.data_dir == tmp_path
    assert app.state.config is fake


def test_config_store_wired_to_data_dir(tmp_path):
    from folio_engine.config import ConfigStore

    app = create_app("secret", tmp_path)
    assert isinstance(app.state.config, ConfigStore)
    assert app.state.config.path == tmp_path / "settings.json"
