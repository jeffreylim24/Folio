from folio_engine.ollama.detect import OllamaStatus, find_ollama, start_ollama


class FakeClient:
    def __init__(self, versions):
        self._versions = list(versions)

    def version(self):
        return self._versions.pop(0) if len(self._versions) > 1 else self._versions[0]


def no_which(_name):
    return None


def test_running_counts_as_installed(tmp_path):
    s = find_ollama(
        FakeClient(["0.9"]), candidates=[tmp_path / "Nope.app"], which=no_which
    )
    assert (s.installed, s.running, s.version, s.app_path) == (True, True, "0.9", None)


def test_installed_not_running(tmp_path):
    app = tmp_path / "Ollama.app"
    app.mkdir()
    s = find_ollama(
        FakeClient([None]), candidates=[tmp_path / "x", app], which=no_which
    )
    assert (s.installed, s.running, s.app_path) == (True, False, str(app))


def test_cli_only_via_which(tmp_path):
    s = find_ollama(
        FakeClient([None]), candidates=[], which=lambda n: "/usr/local/bin/ollama"
    )
    assert s.installed and not s.running and s.app_path == "/usr/local/bin/ollama"


def test_not_installed(tmp_path):
    s = find_ollama(FakeClient([None]), candidates=[tmp_path / "x"], which=no_which)
    assert (s.installed, s.running, s.app_path) == (False, False, None)


def test_start_true_once_version_responds():
    launched = []
    status = OllamaStatus(True, False, None, "/Applications/Ollama.app")
    client = FakeClient([None, None, "0.9"])
    ok = start_ollama(
        status,
        client,
        timeout_s=2,
        launcher=launched.append,
        poll_s=0.01,
        platform="darwin",
    )
    assert ok is True
    assert launched == [["open", "-a", "/Applications/Ollama.app"]]


def test_start_false_on_timeout():
    status = OllamaStatus(True, False, None, "/usr/local/bin/ollama")
    launched = []
    ok = start_ollama(
        status,
        FakeClient([None]),
        timeout_s=0.05,
        launcher=launched.append,
        poll_s=0.01,
    )
    assert ok is False
    assert launched == [["/usr/local/bin/ollama", "serve"]]


def test_start_false_when_launch_fails():
    def boom(_cmd):
        raise OSError("no")

    status = OllamaStatus(True, False, None, "/usr/local/bin/ollama")
    assert (
        start_ollama(status, FakeClient([None]), timeout_s=0.05, launcher=boom) is False
    )


def test_start_noop_when_already_running_or_not_installed():
    launched = []
    assert start_ollama(
        OllamaStatus(True, True, "1", None), FakeClient(["1"]), launcher=launched.append
    )
    assert not start_ollama(
        OllamaStatus(False, False, None, None),
        FakeClient([None]),
        launcher=launched.append,
    )
    assert launched == []


import sys

import pytest

from folio_engine.ollama import detect
from folio_engine.ollama.detect import version_ok


@pytest.mark.parametrize(
    "v, ok",
    [
        ("0.32.12", True),
        ("0.40.9", True),
        ("1.0.0", True),
        ("0.33.0-rc1", True),
        ("0.32.11", False),
        ("0.31.2", False),
        ("dev", True),
        ("", True),
    ],
)
def test_version_ok(v, ok):
    assert version_ok(v) is ok


def test_none_version_not_outdated():
    s = find_ollama(FakeClient([None]), candidates=[], which=no_which)
    assert s.outdated is False


def test_outdated_running(tmp_path):
    app = tmp_path / "Ollama.app"
    app.mkdir()
    s = find_ollama(FakeClient(["0.30.0"]), candidates=[app], which=no_which)
    assert s.outdated is True


def test_updatable_only_for_standard_install(tmp_path, monkeypatch):
    app = tmp_path / "Ollama.app"
    app.mkdir()
    monkeypatch.setattr(detect, "default_candidates", lambda: [app])
    monkeypatch.setattr(sys, "platform", "darwin")
    s = find_ollama(FakeClient(["0.30.0"]), candidates=[app], which=no_which)
    assert s.updatable is True
    s = find_ollama(
        FakeClient(["0.30.0"]), candidates=[], which=lambda _: "/usr/local/bin/ollama"
    )
    assert s.updatable is False
    monkeypatch.setattr(sys, "platform", "linux")
    s = find_ollama(FakeClient(["0.30.0"]), candidates=[app], which=no_which)
    assert s.updatable is False
