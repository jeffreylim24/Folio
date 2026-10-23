import hashlib
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from .client import OllamaClient
from .detect import find_ollama, start_ollama

RELEASE_URL = "https://github.com/ollama/ollama/releases/latest/download"
ASSETS = {"macos": "Ollama-darwin.zip", "windows": "OllamaSetup.exe"}
CHUNK = 1024 * 1024

MSG_NETWORK = "Couldn't download Ollama. Check your internet connection and try again."
MSG_CORRUPT = "The download was corrupted. Please try again."
MSG_INSTALL = "Ollama couldn't be installed. Please try again."
MSG_STOP = "Folio couldn't close Ollama to update it. Quit Ollama and try again."
MSG_START = {
    "macos": (
        "Ollama was installed but didn't start. "
        "Try opening it from your Applications folder."
    ),
    "windows": (
        "Ollama was installed but didn't start. Try opening it from the Start menu."
    ),
}


@dataclass
class InstallStatus:
    state: Literal[
        "idle", "stopping", "downloading", "installing", "starting", "done", "error"
    ]
    progress: float
    message: str | None


class InstallError(Exception):
    """Carries a plain-English message for the user."""


def parse_checksum(text: str, filename: str) -> str | None:
    for line in text.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, name = parts
        if name.strip().lstrip("*").replace("\\", "/").rsplit("/", 1)[-1] == filename:
            return digest.lower()
    return None


def macos_install_fn(
    dest_dir: Path | None = None,
) -> Callable[[Path], None]:
    """Unzip Ollama.app into dest_dir (default /Applications, else ~/Applications)."""

    def install(zip_path: Path) -> None:
        dests = (
            [dest_dir]
            if dest_dir
            else [Path("/Applications"), Path.home() / "Applications"]
        )
        for i, dest in enumerate(dests):
            try:
                dest.mkdir(parents=True, exist_ok=True)
                # ditto preserves symlinks, permissions and signatures in the bundle
                subprocess.run(
                    ["ditto", "-x", "-k", str(zip_path), str(dest)],
                    check=True,
                    capture_output=True,
                )
                return
            except PermissionError:
                if i == len(dests) - 1:
                    raise
            except subprocess.CalledProcessError as e:
                if b"ermission" in e.stderr and i < len(dests) - 1:
                    continue
                raise

    return install


def windows_install(exe_path: Path) -> None:
    subprocess.run(
        [str(exe_path), "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def macos_replace_fn(app_path: Path) -> Callable[[Path], None]:
    """Swap the Ollama.app at app_path for the one in the downloaded zip."""

    def replace(zip_path: Path) -> None:
        staging = zip_path.parent / "staging"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        old = app_path.with_name(app_path.name + ".old")
        moved = False
        try:
            subprocess.run(
                ["ditto", "-x", "-k", str(zip_path), str(staging)],
                check=True,
                capture_output=True,
            )
            shutil.rmtree(old, ignore_errors=True)
            app_path.rename(old)
            moved = True
            shutil.move(str(staging / "Ollama.app"), str(app_path))
            shutil.rmtree(old, ignore_errors=True)
        except Exception:
            if moved:
                shutil.rmtree(app_path, ignore_errors=True)
                old.rename(app_path)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    return replace


def _wait_stopped(client: OllamaClient, seconds: float, poll_s: float = 0.5) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if client.version() is None:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_s)


def _quiet(cmd: list[str]) -> None:
    kwargs: dict = {"capture_output": True, "check": False}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.run(cmd, check=False, **kwargs)
    except OSError:
        pass


class Installer:
    def __init__(
        self,
        os_name: Literal["macos", "windows"],
        work_dir: Path,
        client: OllamaClient,
        http: httpx.Client | None = None,
        install_fn: Callable[[Path], None] | None = None,
        start_fn: Callable[[], bool] | None = None,
        stop_fn: Callable[[], bool] | None = None,
        replace_fn: Callable[[Path], None] | None = None,
    ):
        self._os = os_name
        self._work_dir = work_dir
        self._client = client
        self._http = http
        self._install_fn = install_fn or (
            macos_install_fn() if os_name == "macos" else windows_install
        )
        self._start_fn = start_fn or self._default_start
        self._stop_fn = stop_fn or self._default_stop
        self._replace_fn = replace_fn
        self._lock = threading.Lock()
        self._status = InstallStatus("idle", 0.0, None)
        self._thread: threading.Thread | None = None

    def status(self) -> InstallStatus:
        with self._lock:
            return InstallStatus(**self._status.__dict__)

    def start(self, update: bool = False) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._status = InstallStatus(
                "stopping" if update else "downloading", 0.0, None
            )
            self._thread = threading.Thread(
                target=self._run, args=(update,), daemon=True
            )
            self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _set(self, state: str, progress: float | None = None, message=None) -> None:
        with self._lock:
            self._status.state = state  # type: ignore[assignment]
            if progress is not None:
                self._status.progress = progress
            self._status.message = message

    def _default_start(self) -> bool:
        status = find_ollama(self._client)
        return start_ollama(status, self._client)

    def _default_stop(self) -> bool:
        if self._os == "macos":
            _quiet(["osascript", "-e", 'quit app "Ollama"'])
            if _wait_stopped(self._client, 15):
                return True
            _quiet(["pkill", "-x", "ollama"])
            _quiet(["pkill", "-x", "Ollama"])
        else:
            _quiet(["taskkill", "/F", "/IM", "ollama app.exe"])
            _quiet(["taskkill", "/F", "/IM", "ollama.exe"])
        return _wait_stopped(self._client, 5 if self._os == "macos" else 15)

    def _update_fn(self) -> Callable[[Path], None]:
        if self._replace_fn is not None:
            return self._replace_fn
        if self._os == "windows":
            return windows_install  # Inno Setup upgrades in place
        app_path = find_ollama(self._client).app_path
        if not app_path or not app_path.endswith(".app"):
            raise InstallError(MSG_INSTALL)
        return macos_replace_fn(Path(app_path))

    def _run(self, update: bool = False) -> None:
        installer: Path | None = None
        try:
            if update:
                # Resolve the install location while Ollama is still running.
                replace = self._update_fn()
                self._set("stopping")
                if not self._stop_fn():
                    raise InstallError(MSG_STOP)
            installer = self._download()
            self._set("installing")
            try:
                (replace if update else self._install_fn)(installer)
            except (OSError, subprocess.CalledProcessError) as e:
                raise InstallError(MSG_INSTALL) from e
            installer.unlink(missing_ok=True)
            self._set("starting")
            if not self._start_fn():
                raise InstallError(MSG_START[self._os])
            self._set("done", 1.0)
        except InstallError as e:
            self._set("error", message=str(e))
        except Exception:  # noqa: BLE001
            self._set("error", message=MSG_INSTALL)
        finally:
            if installer is not None and self._status.state == "error":
                installer.unlink(missing_ok=True)

    def _download(self) -> Path:
        asset = ASSETS[self._os]
        self._work_dir.mkdir(parents=True, exist_ok=True)
        dest = self._work_dir / asset
        http = self._http or httpx.Client(
            follow_redirects=True, timeout=httpx.Timeout(30.0)
        )
        try:
            resp = http.get(f"{RELEASE_URL}/sha256sum.txt")
            resp.raise_for_status()
            expected = parse_checksum(resp.text, asset)
            if expected is None:
                raise InstallError(MSG_CORRUPT)
            digest = hashlib.sha256()
            with http.stream("GET", f"{RELEASE_URL}/{asset}") as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                done = 0
                with dest.open("wb") as f:
                    for chunk in r.iter_bytes(CHUNK):
                        f.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        if total:
                            self._set("downloading", min(done / total, 1.0))
        except httpx.HTTPError as e:
            dest.unlink(missing_ok=True)
            raise InstallError(MSG_NETWORK) from e
        finally:
            if self._http is None:
                http.close()
        if digest.hexdigest() != expected:
            dest.unlink(missing_ok=True)
            raise InstallError(MSG_CORRUPT)
        return dest


def default_installer(work_dir: Path, client: OllamaClient) -> Installer | None:
    if sys.platform == "darwin":
        return Installer("macos", work_dir, client)
    if sys.platform == "win32":
        return Installer("windows", work_dir, client)
    return None
