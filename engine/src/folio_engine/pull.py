import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from .catalog import DISK_HEADROOM_GB, find_model
from .config import ConfigStore
from .ollama.client import OllamaClient, OllamaError

MSG_INTERRUPTED = (
    "The download was interrupted. Check your internet connection "
    "and try again; it will resume where it left off."
)
MSG_OLLAMA_DOWN = (
    "Folio couldn't reach Ollama. Make sure Ollama is running "
    "and try again; the download will resume where it left off."
)


def _ollama_error_text(response: httpx.Response) -> str:
    """Ollama's own error message from a failed response, if it sent one."""
    try:
        err = response.json().get("error")
    except (ValueError, AttributeError, httpx.ResponseNotRead):
        err = None
    if isinstance(err, str) and err.strip():
        return err.strip()[:200]
    return f"it answered with error {response.status_code}."


@dataclass
class PullStatus:
    state: Literal["idle", "downloading", "stalled", "done", "error"]
    model: str | None
    completed_bytes: int
    total_bytes: int
    error: str | None
    resuming: bool = False


GB = 1024**3
PROGRESS_WRITE_EVERY_S = 5.0


class PullManager:
    def __init__(
        self,
        client: OllamaClient,
        config: ConfigStore,
        free_disk_gb: Callable[[], float],
        progress_path: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
        stall_after_s: float = 60.0,
    ):
        self._client = client
        self._config = config
        self._free_disk_gb = free_disk_gb
        self._progress_path = progress_path
        self._clock = clock
        self._stall_after_s = stall_after_s
        self._last_progress_at = 0.0
        self._last_fresh_bytes = 0
        self._last_write_at: float | None = None
        self._seed_bytes = 0
        self._lock = threading.Lock()
        self._status = PullStatus("idle", None, 0, 0, None)
        self._thread: threading.Thread | None = None
        self._resume_thread: threading.Thread | None = None

    def status(self) -> PullStatus:
        with self._lock:
            status = PullStatus(**self._status.__dict__)
            if (
                status.state == "downloading"
                and self._clock() - self._last_progress_at >= self._stall_after_s
            ):
                status.state = "stalled"
            return status

    def _read_progress(self, model: str) -> tuple[int, int]:
        """Last saved (completed, total) bytes for this model, else (0, 0)."""
        if self._progress_path is None:
            return 0, 0
        try:
            data = json.loads(self._progress_path.read_text())
            if data["model"] == model:
                return int(data["completed_bytes"]), int(data["total_bytes"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return 0, 0

    def _write_progress(self, model: str, completed: int, total: int) -> None:
        if self._progress_path is None:
            return
        try:
            tmp = self._progress_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"model": model, "completed_bytes": completed, "total_bytes": total}
                )
            )
            os.replace(tmp, self._progress_path)
        except OSError:
            pass  # progress memory is best-effort

    def _clear_progress(self) -> None:
        if self._progress_path is None:
            return
        try:
            self._progress_path.unlink(missing_ok=True)
        except OSError:
            pass

    def join(self, timeout: float | None = None) -> None:
        """Wait for a background resume check, then for the pull itself."""
        for attr in ("_resume_thread", "_thread"):
            thread = getattr(self, attr)
            if thread is not None:
                thread.join(timeout)

    def start(self, model: str, size_gb: float | None) -> None:
        """Begin (or resume) a pull in the background. No-op if one is running.

        `size_gb` enables the full free-space check; pass None when resuming,
        since part of the model may already be on disk (Ollama reports its own
        disk-full error if space really runs out).
        """
        seeded, seeded_total = self._read_progress(model)
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if size_gb is not None:
                remaining_gb = max(size_gb - seeded / GB, 0)
                needed = remaining_gb + DISK_HEADROOM_GB
                free = self._free_disk_gb()
                if free < needed:
                    short = round(needed - free, 1)
                    self._status = PullStatus(
                        "error",
                        model,
                        0,
                        0,
                        f"There isn't enough free disk space for this model. "
                        f"Free up {short:g} GB and try again.",
                    )
                    return
            self._status = PullStatus(
                "downloading", model, seeded, seeded_total, None, seeded > 0
            )
            self._seed_bytes = seeded
            self._last_progress_at = self._clock()
            self._last_fresh_bytes = 0
            self._last_write_at = None
            self._thread = threading.Thread(
                target=self._run, args=(model,), daemon=True
            )
            self._thread.start()

    def resume_if_needed(self) -> None:
        """On startup: continue an unfinished download. Never raises."""
        try:
            settings = self._config.load()
            if settings.provider != "ollama" or not settings.model:
                return
            model = settings.model
            if find_model(model) is None:
                return  # only catalog models are supported
            if model in self._client.list_models():
                with self._lock:
                    self._status = PullStatus("done", model, 0, 0, None)
                return
            # Resuming: part of the model may already be on disk.
            self.start(model, None)
        except Exception:  # noqa: BLE001
            # Ollama may simply not be running yet; stay idle.
            return

    def resume_in_background(self) -> None:
        """Run resume_if_needed off the caller's thread, if a resume could apply.

        Cheap to call often: does nothing unless the pull is idle, settings
        name an Ollama model, and no other resume check is running.
        """
        with self._lock:
            if self._status.state != "idle":
                return
            if self._resume_thread is not None and self._resume_thread.is_alive():
                return
            settings = self._config.load()
            if settings.provider != "ollama" or not settings.model:
                return
            self._resume_thread = threading.Thread(
                target=self.resume_if_needed, daemon=True
            )
            self._resume_thread.start()

    def _set_error(self, message: str) -> None:
        with self._lock:
            self._status.state = "error"
            self._status.error = message

    def _run(self, model: str) -> None:
        layers: dict[str, tuple[int, int]] = {}
        try:
            for event in self._client.pull(model):
                if event.status == "success":
                    with self._lock:
                        self._status.state = "done"
                    self._clear_progress()
                    return
                if event.digest and event.total:
                    layers[event.digest] = (event.total, event.completed or 0)
                    total = sum(t for t, _ in layers.values())
                    fresh = sum(c for _, c in layers.values())
                    with self._lock:
                        now = self._clock()
                        if fresh > self._last_fresh_bytes:
                            self._last_fresh_bytes = fresh
                            self._last_progress_at = now
                        if self._status.resuming and fresh < self._seed_bytes:
                            continue  # keep showing the saved, higher numbers
                        self._status.resuming = False
                        self._status.total_bytes = total
                        self._status.completed_bytes = fresh
                        due = (
                            self._last_write_at is None
                            or now - self._last_write_at >= PROGRESS_WRITE_EVERY_S
                        )
                        if due:
                            self._last_write_at = now
                    if due:
                        self._write_progress(model, fresh, total)
            self._set_error(MSG_INTERRUPTED)
        except OllamaError as e:
            self._set_error(f"Ollama couldn't download the model: {e}")
        except httpx.HTTPStatusError as e:
            self._set_error(
                f"Ollama couldn't download the model: {_ollama_error_text(e.response)}"
            )
        except httpx.ConnectError:
            self._set_error(MSG_OLLAMA_DOWN)
        except Exception:  # noqa: BLE001
            self._set_error(MSG_INTERRUPTED)
