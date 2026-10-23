import threading
import time

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


def run(mgr, model="qwen3.5:9b-q4_K_M", size=6.6):
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
    assert s.model == "qwen3.5:9b-q4_K_M"


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
    assert client.pulls == ["qwen3.5:9b-q4_K_M", "qwen3.5:9b-q4_K_M"]


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
    mgr.start("qwen3.5:9b-q4_K_M", 6.6)
    s = mgr.status()
    assert s.state == "error"
    assert "5.6 GB" in s.error
    assert client.pulls == []


def test_resume_if_needed_starts_pull(tmp_path):
    client = FakeClient([p("success")], installed=[])
    mgr = make(tmp_path, client, model="qwen3.5:9b-q4_K_M")
    mgr.resume_if_needed()
    mgr.join(5)
    assert client.pulls == ["qwen3.5:9b-q4_K_M"]
    assert mgr.status().state == "done"


def test_resume_if_needed_model_present(tmp_path):
    client = FakeClient(installed=["qwen3.5:9b-q4_K_M"])
    mgr = make(tmp_path, client, model="qwen3.5:9b-q4_K_M")
    mgr.resume_if_needed()
    assert mgr.status().state == "done"
    assert client.pulls == []


def test_resume_if_needed_never_raises(tmp_path):
    client = FakeClient(list_error=httpx.ConnectError("down"))
    mgr = make(tmp_path, client, model="qwen3.5:9b-q4_K_M")
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
    r = tc.put("/setup/model", json={"model": "qwen3.5:4b-q4_K_M"}, headers=AUTH)
    assert r.status_code == 202
    mgr.join(5)
    saved = ConfigStore(tmp_path / "settings.json").load()
    assert (saved.provider, saved.model, saved.setup_complete) == (
        "ollama",
        "qwen3.5:4b-q4_K_M",
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
        Settings(provider="ollama", model="qwen3.5:4b-q4_K_M")
    )
    assert tc.post("/setup/pull/retry", headers=AUTH).status_code == 202
    mgr.join(5)
    assert client.pulls == ["qwen3.5:4b-q4_K_M"]


def test_pull_routes_require_token(tmp_path):
    tc, _ = app_with(tmp_path, FakeClient())
    assert tc.get("/setup/pull").status_code == 401


def test_startup_calls_resume_in_background(tmp_path):
    class Spy:
        called = False

        def resume_in_background(self):
            Spy.called = True
            raise RuntimeError("must not break startup")

    with TestClient(create_app("secret", tmp_path, pull_manager=Spy())) as tc:
        assert tc.get("/health", headers=AUTH).status_code == 200
    assert Spy.called


class SlowListClient(FakeClient):
    """list_models blocks until released, like an Ollama that hangs."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.release = threading.Event()

    def list_models(self):
        self.release.wait(5)
        return super().list_models()


def test_startup_resume_does_not_block_startup(tmp_path):
    client = SlowListClient(events=[p("success")])
    mgr = make(tmp_path, client, model="qwen3.5:4b-q4_K_M")
    app = create_app("secret", tmp_path, pull_manager=mgr, ollama_client=client)
    began = time.monotonic()
    with TestClient(app) as tc:
        # Startup finished and serves requests while list_models is stuck.
        assert tc.get("/health", headers=AUTH).status_code == 200
        assert time.monotonic() - began < 2
        client.release.set()
        mgr.join(5)
    assert client.pulls == ["qwen3.5:4b-q4_K_M"]


class SwitchableClient(FakeClient):
    """Ollama that is down until `up` is set."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.up = False

    def version(self):
        return "0.9" if self.up else None

    def list_models(self):
        if not self.up:
            raise httpx.ConnectError("down")
        return super().list_models()


def test_ollama_down_at_start_then_started_begins_pull(tmp_path):
    client = SwitchableClient(events=[p("success")])
    mgr = make(tmp_path, client, model="qwen3.5:4b-q4_K_M")
    app = create_app("secret", tmp_path, pull_manager=mgr, ollama_client=client)
    with TestClient(app) as tc:
        mgr.join(5)
        assert mgr.status().state == "idle" and client.pulls == []
        client.up = True
        r = tc.post("/setup/ollama/start", headers=AUTH)
        assert r.json() == {"running": True}
        mgr.join(5)
        assert client.pulls == ["qwen3.5:4b-q4_K_M"]
        assert tc.get("/setup/pull", headers=AUTH).json()["state"] == "done"


def test_get_pull_resumes_idle_download_once_ollama_is_up(tmp_path):
    client = SwitchableClient(events=[p("success")])
    mgr = make(tmp_path, client, model="qwen3.5:4b-q4_K_M")
    tc = TestClient(
        create_app("secret", tmp_path, pull_manager=mgr, ollama_client=client)
    )
    assert tc.get("/setup/pull", headers=AUTH).json()["state"] == "idle"
    mgr.join(5)
    assert client.pulls == []
    client.up = True  # e.g. the user opened Ollama themselves
    tc.get("/setup/pull", headers=AUTH)
    mgr.join(5)
    assert client.pulls == ["qwen3.5:4b-q4_K_M"]


def test_get_state_resumes_idle_download(tmp_path):
    client = SwitchableClient(events=[p("success")])
    client.up = True
    mgr = make(tmp_path, client, model="qwen3.5:4b-q4_K_M")
    tc = TestClient(
        create_app("secret", tmp_path, pull_manager=mgr, ollama_client=client)
    )
    tc.get("/setup/state", headers=AUTH)
    mgr.join(5)
    assert client.pulls == ["qwen3.5:4b-q4_K_M"]


def test_resume_in_background_skips_without_ollama_model(tmp_path):
    client = FakeClient(installed=[])
    config = ConfigStore(tmp_path / "settings.json")
    config.save(Settings(provider="anthropic", model="x"))
    mgr = PullManager(client, config, lambda: 100)
    mgr.resume_in_background()
    mgr.join(5)
    assert client.pulls == [] and mgr.status().state == "idle"


def test_retry_with_partial_bytes_under_low_disk_proceeds(tmp_path):
    # 3 GB free is less than the full 6.6 GB + headroom, but most of the
    # model is already on disk, so retry must not demand the full size again.
    client = FakeClient([p("pulling a", "a", 100, 80), httpx.ReadError("boom")])
    mgr = make(tmp_path, client, free=3, model="qwen3.5:9b-q4_K_M")
    tc = TestClient(
        create_app("secret", tmp_path, pull_manager=mgr, ollama_client=client)
    )
    mgr.start("qwen3.5:9b-q4_K_M", None)
    mgr.join(5)
    assert mgr.status().state == "error"
    client.events = [p("success")]
    assert tc.post("/setup/pull/retry", headers=AUTH).status_code == 202
    mgr.join(5)
    assert client.pulls == ["qwen3.5:9b-q4_K_M", "qwen3.5:9b-q4_K_M"]
    assert mgr.status().state == "done"


def test_resume_under_low_disk_proceeds(tmp_path):
    client = FakeClient([p("success")], installed=[])
    mgr = make(tmp_path, client, free=1, model="qwen3.5:9b-q4_K_M")
    mgr.resume_if_needed()
    mgr.join(5)
    assert client.pulls == ["qwen3.5:9b-q4_K_M"]


def test_put_model_still_checks_full_size(tmp_path):
    client = FakeClient([p("success")])
    mgr = make(tmp_path, client, free=3)
    tc = TestClient(
        create_app("secret", tmp_path, pull_manager=mgr, ollama_client=client)
    )
    tc.put("/setup/model", json={"model": "qwen3.5:9b-q4_K_M"}, headers=AUTH)
    mgr.join(5)
    assert client.pulls == []
    assert "5.6 GB" in mgr.status().error


def test_http_status_error_includes_ollama_body(tmp_path):
    req = httpx.Request("POST", "http://x/api/pull")
    resp = httpx.Response(
        404, json={"error": "pull model manifest: file does not exist"}, request=req
    )
    err = httpx.HTTPStatusError("bad", request=req, response=resp)
    mgr = make(tmp_path, FakeClient([err]))
    run(mgr)
    s = mgr.status()
    assert s.state == "error"
    assert "file does not exist" in s.error
    assert "internet" not in s.error


class BlockingClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.release = threading.Event()

    def pull(self, model):
        self.pulls.append(model)
        yield p("pulling a", "a", 100, 10)
        self.release.wait(5)
        yield p("success")


def test_second_start_during_pull_is_noop(tmp_path):
    client = BlockingClient()
    mgr = make(tmp_path, client)
    mgr.start("qwen3.5:4b-q4_K_M", 3.3)
    mgr.start("qwen3.5:9b-q4_K_M", 6.6)
    client.release.set()
    mgr.join(5)
    assert client.pulls == ["qwen3.5:4b-q4_K_M"]


def test_put_other_model_while_downloading_409(tmp_path):
    client = BlockingClient()
    tc, mgr = app_with(tmp_path, client)
    store = ConfigStore(tmp_path / "settings.json")
    store.save(Settings(provider="ollama", model="qwen3.5:4b-q4_K_M"))
    mgr.start("qwen3.5:4b-q4_K_M", 3.3)
    r = tc.put("/setup/model", json={"model": "qwen3.5:9b-q4_K_M"}, headers=AUTH)
    assert r.status_code == 409
    assert "already downloading" in r.json()["detail"]
    assert store.load().model == "qwen3.5:4b-q4_K_M"
    r = tc.put("/setup/model", json={"model": "qwen3.5:4b-q4_K_M"}, headers=AUTH)
    assert r.status_code == 202
    client.release.set()
    mgr.join(5)
    assert client.pulls == ["qwen3.5:4b-q4_K_M"]


def test_put_model_resets_setup_complete(tmp_path):
    tc, mgr = app_with(tmp_path, FakeClient([p("success")]))
    store = ConfigStore(tmp_path / "settings.json")
    store.save(Settings(provider="ollama", model="qwen3.5:4b-q4_K_M", setup_complete=True))
    tc.put("/setup/model", json={"model": "qwen3.5:9b-q4_K_M"}, headers=AUTH)
    mgr.join(5)
    assert store.load().setup_complete is False


def test_resume_skips_uncatalogued_model(tmp_path):
    client = FakeClient([p("success")], installed=[])
    mgr = make(tmp_path, client, model="qwen3:14b")
    mgr.resume_if_needed()
    mgr.join(5)
    assert client.pulls == [] and mgr.status().state == "idle"
