import hashlib
from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from folio_engine.ollama.install import (
    Installer,
    _wait_stopped,
    macos_replace_fn,
    parse_checksum,
)
from folio_engine.server import create_app

BASE = "https://github.com/ollama/ollama/releases/latest/download"
PAYLOAD = b"x" * (2 * 1024 * 1024 + 5)
SHA = hashlib.sha256(PAYLOAD).hexdigest()


class FakeClient:
    def version(self):
        return None


def make(tmp_path, os_name="macos", install_fn=None, start_fn=None):
    calls = []

    def default_install(path):
        calls.append(path)

    inst = Installer(
        os_name,
        tmp_path,
        FakeClient(),
        install_fn=install_fn or default_install,
        start_fn=start_fn or (lambda: True),
    )
    return inst, calls


def run(inst):
    inst.start()
    inst.join(10)
    return inst.status()


def mock_assets(sha_line, asset="Ollama-darwin.zip"):
    respx.get(f"{BASE}/sha256sum.txt").mock(
        return_value=httpx.Response(200, text=sha_line)
    )
    respx.get(f"{BASE}/{asset}").mock(return_value=httpx.Response(200, content=PAYLOAD))


def test_parse_checksum_matches_basename():
    text = f"{'a' * 64}  ./other.zip\n{SHA}  ./Ollama-darwin.zip\n"
    assert parse_checksum(text, "Ollama-darwin.zip") == SHA
    assert parse_checksum(text, "missing.zip") is None


@respx.mock
def test_checksum_mismatch_errors(tmp_path):
    mock_assets(f"{'0' * 64}  Ollama-darwin.zip\n")
    inst, calls = make(tmp_path)
    st = run(inst)
    assert st.state == "error"
    assert "download was corrupted" in st.message
    assert calls == []
    assert list(tmp_path.iterdir()) == []


@respx.mock
def test_happy_path_reaches_done(tmp_path):
    mock_assets(f"{SHA}  ./Ollama-darwin.zip\n")
    inst, calls = make(tmp_path)
    st = run(inst)
    assert st.state == "done"
    assert st.progress == 1
    assert len(calls) == 1
    assert not calls[0].exists()  # installer deleted after success


@respx.mock
def test_download_failure_message(tmp_path):
    respx.get(f"{BASE}/sha256sum.txt").mock(side_effect=httpx.ConnectError("boom"))
    inst, calls = make(tmp_path)
    st = run(inst)
    assert st.state == "error"
    assert "internet connection" in st.message
    assert calls == []


@respx.mock
def test_start_failure_message(tmp_path):
    mock_assets(f"{SHA}  Ollama-darwin.zip\n")
    inst, _ = make(tmp_path, start_fn=lambda: False)
    st = run(inst)
    assert st.state == "error"
    assert "installed but didn't start" in st.message


@respx.mock
def test_install_failure_message(tmp_path):
    mock_assets(f"{SHA}  Ollama-darwin.zip\n")

    def boom(path):
        raise OSError("nope")

    inst, _ = make(tmp_path, install_fn=boom)
    st = run(inst)
    assert st.state == "error"
    assert st.message


@respx.mock
def test_windows_uses_exe_asset(tmp_path):
    mock_assets(f"{SHA}  OllamaSetup.exe\n", asset="OllamaSetup.exe")
    inst, calls = make(tmp_path, os_name="windows")
    assert run(inst).state == "done"
    assert calls[0].name == "OllamaSetup.exe"


def test_route_install_and_status(tmp_path):
    inst, _ = make(tmp_path)
    inst.start = lambda: None
    client = TestClient(create_app("secret", tmp_path, installer=inst))
    h = {"Authorization": "Bearer secret"}
    assert client.post("/setup/ollama/install", headers=h).status_code == 202
    r = client.get("/setup/ollama/install", headers=h)
    assert r.json() == {"state": "idle", "progress": 0.0, "message": None}
    assert client.post("/setup/ollama/install").status_code == 401


def test_route_unsupported_os(tmp_path):
    client = TestClient(create_app("secret", tmp_path, installer=None))
    r = client.post("/setup/ollama/install", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 400


@respx.mock
def test_missing_checksum_entry_errors(tmp_path):
    mock_assets(f"{SHA}  SomethingElse.zip\n")
    inst, calls = make(tmp_path)
    st = run(inst)
    assert st.state == "error"
    assert "download was corrupted" in st.message
    assert calls == []
    assert list(tmp_path.iterdir()) == []


@respx.mock
def test_start_failure_message_is_platform_specific(tmp_path):
    mock_assets(f"{SHA}  ./Ollama-darwin.zip\n")
    inst, _ = make(tmp_path / "mac", start_fn=lambda: False)
    assert run(inst).message == (
        "Ollama was installed but didn't start. "
        "Try opening it from your Applications folder."
    )
    mock_assets(f"{SHA}  ./OllamaSetup.exe\n", asset="OllamaSetup.exe")
    inst, _ = make(tmp_path / "win", os_name="windows", start_fn=lambda: False)
    message = run(inst).message
    assert "Applications" not in message
    assert message == (
        "Ollama was installed but didn't start. Try opening it from the Start menu."
    )


def test_update_stops_then_replaces_then_starts(tmp_path):
    order = []
    inst = Installer(
        "macos",
        tmp_path,
        FakeClient(),
        install_fn=lambda p: order.append("install"),
        start_fn=lambda: order.append("start") or True,
        stop_fn=lambda: order.append("stop") or True,
        replace_fn=lambda p: order.append("replace"),
    )
    with respx.mock:
        mock_assets(f"{SHA}  Ollama-darwin.zip\n")
        inst.start(update=True)
        inst.join(10)
    assert order == ["stop", "replace", "start"]  # download happens before stop
    assert inst.status().state == "done"


def test_update_stop_fails(tmp_path):
    replaced = []
    inst = Installer(
        "macos",
        tmp_path,
        FakeClient(),
        start_fn=lambda: True,
        stop_fn=lambda: False,
        replace_fn=replaced.append,
    )
    with respx.mock:
        mock_assets(f"{SHA}  Ollama-darwin.zip\n")
        inst.start(update=True)
        inst.join(10)
    st = inst.status()
    assert st.state == "error"
    assert st.message == (
        "Folio couldn't close Ollama to update it. Quit Ollama and try again."
    )
    assert replaced == []


def test_update_replace_failure_restarts_old_ollama(tmp_path):
    order = []

    def bad_replace(p):
        raise OSError("boom")

    inst = Installer(
        "macos",
        tmp_path,
        FakeClient(),
        start_fn=lambda: order.append("start") or True,
        stop_fn=lambda: order.append("stop") or True,
        replace_fn=bad_replace,
    )
    with respx.mock:
        mock_assets(f"{SHA}  Ollama-darwin.zip\n")
        inst.start(update=True)
        inst.join(10)
    assert order == ["stop", "start"]
    assert inst.status().state == "error"


def test_update_download_failure_never_stops(tmp_path):
    order = []
    inst = Installer(
        "macos",
        tmp_path,
        FakeClient(),
        start_fn=lambda: order.append("start") or True,
        stop_fn=lambda: order.append("stop") or True,
        replace_fn=lambda p: order.append("replace"),
    )
    with respx.mock:
        mock_assets(f"{'0' * 64}  Ollama-darwin.zip\n")
        inst.start(update=True)
        inst.join(10)
    assert order == []
    assert inst.status().state == "error"


# --- default replace / stop ------------------------------------------------


def _bundle(path, marker):
    path.mkdir(parents=True)
    (path / "marker").write_text(marker)


def _fake_ditto(marker):
    def run(cmd, **kw):
        dest = Path(cmd[-1])
        _bundle(dest / "Ollama.app", marker)

    return run


def test_replace_success(tmp_path):
    app = tmp_path / "Apps" / "Ollama.app"
    _bundle(app, "old")
    zip_path = tmp_path / "z.zip"
    zip_path.write_bytes(b"z")
    macos_replace_fn(app, runner=_fake_ditto("new"))(zip_path)
    assert (app / "marker").read_text() == "new"
    assert sorted(p.name for p in app.parent.iterdir()) == ["Ollama.app"]


def test_replace_failure_restores_original(tmp_path, monkeypatch):
    app = tmp_path / "Apps" / "Ollama.app"
    _bundle(app, "old")
    zip_path = tmp_path / "z.zip"
    zip_path.write_bytes(b"z")
    real_rename = Path.rename

    def flaky(self, target):
        if self.name == "Ollama.app" and self.parent.name.startswith(".folio"):
            raise OSError("move failed")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    with pytest.raises(OSError, match="move failed"):
        macos_replace_fn(app, runner=_fake_ditto("new"))(zip_path)
    assert (app / "marker").read_text() == "old"
    assert sorted(p.name for p in app.parent.iterdir()) == ["Ollama.app"]


def test_replace_rollback_failure_keeps_original_error(tmp_path, monkeypatch):
    app = tmp_path / "Apps" / "Ollama.app"
    _bundle(app, "old")
    zip_path = tmp_path / "z.zip"
    zip_path.write_bytes(b"z")
    real_rename = Path.rename

    def flaky(self, target):
        if self.name == "Ollama.app" and self.parent.name.startswith(".folio"):
            raise OSError("move failed")
        if self.name == "Ollama.app.old":
            raise OSError("rollback failed")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    with pytest.raises(OSError, match="move failed"):
        macos_replace_fn(app, runner=_fake_ditto("new"))(zip_path)
    assert (app.parent / "Ollama.app.old" / "marker").read_text() == "old"


class SeqClient:
    def __init__(self, versions):
        self.versions = list(versions)

    def version(self):
        v = self.versions.pop(0) if len(self.versions) > 1 else self.versions[0]
        return v


def test_wait_stopped():
    assert _wait_stopped(SeqClient(["1", None]), 1, poll_s=0.01) is True
    assert _wait_stopped(SeqClient(["1"]), 0.05, poll_s=0.01) is False


def _stop_installer(tmp_path, client, os_name="macos"):
    cmds = []
    inst = Installer(
        os_name,
        tmp_path,
        client,
        run_fn=lambda cmd, **kw: cmds.append(cmd),
    )
    inst._quit_wait_s = inst._kill_wait_s = 0.05
    inst._poll_s = 0.01
    return inst, cmds


def test_default_stop_quits_politely(tmp_path):
    inst, cmds = _stop_installer(tmp_path, SeqClient(["1", None]))
    assert inst._default_stop() is True
    assert [c[0] for c in cmds] == ["osascript"]


def test_default_stop_escalates_to_pkill(tmp_path):
    class Client:
        def __init__(self):
            self.killed = False

        def version(self):
            return None if self.killed else "1"

    client = Client()
    inst, cmds = _stop_installer(tmp_path, client)
    inst._run_fn = lambda cmd, **kw: (
        cmds.append(cmd),
        setattr(client, "killed", cmd[0] == "pkill"),
    )
    assert inst._default_stop() is True
    assert [c[0] for c in cmds] == ["osascript", "pkill", "pkill"]


def test_default_stop_gives_up(tmp_path):
    inst, _ = _stop_installer(tmp_path, SeqClient(["1"]))
    assert inst._default_stop() is False


def test_default_stop_windows(tmp_path):
    inst, cmds = _stop_installer(tmp_path, SeqClient([None]), "windows")
    assert inst._default_stop() is True
    assert [c[0] for c in cmds] == ["taskkill", "taskkill"]
