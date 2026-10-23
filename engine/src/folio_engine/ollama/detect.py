import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .client import OllamaClient

MIN_OLLAMA_VERSION = (0, 32, 12)


def version_ok(version: str | None) -> bool:
    """True if the version is new enough (or can't be read, so we don't block)."""
    m = re.match(r"\d+\.\d+\.\d+", version or "")
    if m is None:
        return True
    parsed = tuple(int(x) for x in m.group().split("."))
    if parsed == (0, 0, 0):
        return True  # source builds report 0.0.0; treat as unknown
    return parsed >= MIN_OLLAMA_VERSION


@dataclass
class OllamaStatus:
    installed: bool
    running: bool
    version: str | None
    app_path: str | None
    outdated: bool = False
    updatable: bool = False


def default_candidates() -> list[Path]:
    if sys.platform == "darwin":
        return [
            Path("/Applications/Ollama.app"),
            Path.home() / "Applications" / "Ollama.app",
        ]
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            return [Path(local) / "Programs" / "Ollama" / "ollama app.exe"]
    return []


def find_ollama(
    client: OllamaClient,
    candidates: Iterable[Path] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> OllamaStatus:
    paths = default_candidates() if candidates is None else candidates
    app_path = next((str(p) for p in paths if p.exists()), None) or which("ollama")
    version = client.version()
    running = version is not None
    standard = {str(p) for p in default_candidates()}
    return OllamaStatus(
        installed=running or app_path is not None,
        running=running,
        version=version,
        app_path=app_path,
        outdated=running and not version_ok(version),
        updatable=sys.platform in ("darwin", "win32") and app_path in standard,
    )


def _launch_command(app_path: str, platform: str) -> list[str]:
    if platform == "darwin" and app_path.endswith(".app"):
        return ["open", "-a", app_path]
    if app_path.lower().endswith("ollama app.exe"):
        return [app_path]
    return [app_path, "serve"]


def _popen_detached(cmd: list[str]) -> None:
    kwargs: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def start_ollama(
    status: OllamaStatus,
    client: OllamaClient,
    timeout_s: float = 30,
    launcher: Callable[[list[str]], None] = _popen_detached,
    poll_s: float = 0.5,
    platform: str = sys.platform,
) -> bool:
    if status.running:
        return True
    if not status.app_path:
        return False
    try:
        launcher(_launch_command(status.app_path, platform))
    except OSError:
        return False
    deadline = time.monotonic() + timeout_s
    while True:
        if client.version() is not None:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_s)
