import httpx
from fastapi.testclient import TestClient

from folio_engine.config import ConfigStore, Settings
from folio_engine.ollama.client import OllamaError, PullProgress
from folio_engine.pull import PullManager
from folio_engine.server import create_app

AUTH = {"Authorization": "Bearer secret"}


class FakeClient:
    def __init__(self, events=(), installed=(), list_error=None):
        self.events = list(events)
        self.installed = list(installed)
        self.list_error = list_error
        self.pulls: list[str] = []

    def list_models(self):
        if self.list_error:
            raise self.list_error
        return self.installed

    def pull(self, model):
        self.pulls.append(model)
        for e in self.events:
            if isinstance(e, Exception):
                raise e
            yield e


def p(status, digest=None, total=None, completed=None):
    return PullProgress(status, digest, total, completed)


def make(tmp_path, client, free=100.0, model=None):
    config = ConfigStore(tmp_path / "settings.json")
    if model:
        config.save(Settings(provider="ollama", model=model))
    return PullManager(client, config, lambda: free)


def run(mgr, model="qwen3:14b", size=9.3):
    mgr.start(model, size)
    mgr.join(5)


def test_progress_sums_layers(tmp_path):
    client = FakeClient([p("pulling a", "a", 100, 40), p("pulling b", "b", 50, 50)])
    mgr = make(tmp_path, client)
    run(mgr)
    s = mgr.status()
    assert (s.completed_bytes, s.total_bytes) == (90, 150)
    assert s.state == "error"  # stream ended without success


def test_done_when_success(tmp_path):
    client = FakeClient([p("pulling a", "a", 100, 100), p("success")])
    mgr = make(tmp_path, client)
    run(mgr)
    s = mgr.status()
    assert s.state == "done"
    assert s.model == "qwen3:14b"


def test_stream_error_sets_error_state_and_can_resume(tmp_path):
    client = FakeClient([p("pulling a", "a", 100, 40), httpx.ReadError("boom")])
    mgr = make(tmp_path, client)
    run(mgr)
    s = mgr.status()
    assert s.state == "error"
    assert "interrupted" in s.error and "resume" in s.error
    client.events = [p("success")]
    run(mgr)
    assert mgr.status().state == "done"
    assert client.pulls == ["qwen3:14b", "qwen3:14b"]


def test_ollama_error_includes_message(tmp_path):
    client = FakeClient([OllamaError("model not found")])
    mgr = make(tmp_path, client)
    run(mgr)
    assert "model not found" in mgr.status().error


def test_http_status_error_is_error_state(tmp_path):
    req = httpx.Request("POST", "http://x/api/pull")
    err = httpx.HTTPStatusError("bad", request=req, response=httpx.Response(500))
    mgr = make(tmp_path, FakeClient([err]))
    run(mgr)
    assert mgr.status().state == "error"


def test_start_refuses_when_disk_low(tmp_path):
    client = FakeClient([p("success")])
    mgr = make(tmp_path, client, free=3)
    mgr.start("qwen3:14b", 9.3)
    s = mgr.status()
    assert s.state == "error"
    assert "8.3 GB" in s.error
    assert client.pulls == []


def test_resume_if_needed_starts_pull(tmp_path):
    client = FakeClient([p("success")], installed=[])
    mgr = make(tmp_path, client, model="qwen3:14b")
    mgr.resume_if_needed()
    mgr.join(5)
    assert client.pulls == ["qwen3:14b"]
    assert mgr.status().state == "done"


def test_resume_if_needed_model_present(tmp_path):
    client = FakeClient(installed=["qwen3:14b"])
    mgr = make(tmp_path, client, model="qwen3:14b")
    mgr.resume_if_needed()
    assert mgr.status().state == "done"
    assert client.pulls == []


def test_resume_if_needed_never_raises(tmp_path):
    client = FakeClient(list_error=httpx.ConnectError("down"))
    mgr = make(tmp_path, client, model="qwen3:14b")
    mgr.resume_if_needed()
    assert mgr.status().state == "idle"


def test_resume_if_needed_skips_other_provider(tmp_path):
    client = FakeClient(installed=[])
    config = ConfigStore(tmp_path / "settings.json")
    config.save(Settings(provider="anthropic", model="x"))
    mgr = PullManager(client, config, lambda: 100)
    mgr.resume_if_needed()
    assert client.pulls == [] and mgr.status().state == "idle"


def app_with(tmp_path, client):
    mgr = make(tmp_path, client)
    app = create_app("secret", tmp_path, pull_manager=mgr, ollama_client=client)
    return TestClient(app), mgr


def test_put_model_saves_and_starts(tmp_path):
    client = FakeClient([p("success")])
    tc, mgr = app_with(tmp_path, client)
    r = tc.put("/setup/model", json={"model": "qwen3:8b"}, headers=AUTH)
    assert r.status_code == 202
    mgr.join(5)
    saved = ConfigStore(tmp_path / "settings.json").load()
    assert (saved.provider, saved.model, saved.setup_complete) == (
        "ollama",
        "qwen3:8b",
        False,
    )
    assert tc.get("/setup/pull", headers=AUTH).json()["state"] == "done"


def test_put_model_unknown_tag_400(tmp_path):
    tc, _ = app_with(tmp_path, FakeClient())
    r = tc.put("/setup/model", json={"model": "nope:1b"}, headers=AUTH)
    assert r.status_code == 400


def test_retry_without_model_400(tmp_path):
    tc, _ = app_with(tmp_path, FakeClient())
    assert tc.post("/setup/pull/retry", headers=AUTH).status_code == 400


def test_retry_restarts_pull(tmp_path):
    client = FakeClient([p("success")])
    tc, mgr = app_with(tmp_path, client)
    ConfigStore(tmp_path / "settings.json").save(
        Settings(provider="ollama", model="qwen3:8b")
    )
    assert tc.post("/setup/pull/retry", headers=AUTH).status_code == 202
    mgr.join(5)
    assert client.pulls == ["qwen3:8b"]


def test_pull_routes_require_token(tmp_path):
    tc, _ = app_with(tmp_path, FakeClient())
    assert tc.get("/setup/pull").status_code == 401


def test_startup_calls_resume_if_needed(tmp_path):
    class Spy:
        called = False

        def resume_if_needed(self):
            Spy.called = True
            raise RuntimeError("must not break startup")

    with TestClient(create_app("secret", tmp_path, pull_manager=Spy())) as tc:
        assert tc.get("/health", headers=AUTH).status_code == 200
    assert Spy.called
