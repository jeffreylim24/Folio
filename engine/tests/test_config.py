import json

from folio_engine.config import ConfigStore, Settings


def test_load_missing_returns_defaults(tmp_path):
    store = ConfigStore(tmp_path / "settings.json")
    assert store.load() == Settings()


def test_round_trip(tmp_path):
    store = ConfigStore(tmp_path / "settings.json")
    settings = Settings(
        provider="openai_compatible",
        model="llama3",
        base_url="http://localhost:8080/v1",
        setup_complete=True,
    )
    store.save(settings)
    assert store.load() == settings


def test_save_is_atomic(tmp_path):
    path = tmp_path / "nested" / "settings.json"
    store = ConfigStore(path)
    store.save(Settings(provider="ollama", setup_complete=True))
    assert not (path.parent / "settings.json.tmp").exists()
    data = json.loads(path.read_text())
    assert data["provider"] == "ollama"
    assert data["setup_complete"] is True


def test_corrupt_file_returns_defaults_and_backs_up(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not json")
    settings = ConfigStore(path).load()
    assert settings == Settings()
    backup = tmp_path / "settings.json.corrupt"
    assert backup.exists()
    assert backup.read_text() == "{not json"


def test_unknown_keys_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"provider": "gemini", "future_key": 42}))
    settings = ConfigStore(path).load()
    assert settings == Settings(provider="gemini")
