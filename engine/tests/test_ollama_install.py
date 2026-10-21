import hashlib

import httpx
import respx
from fastapi.testclient import TestClient

from folio_engine.ollama.install import Installer, parse_checksum
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
