import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_PORT = 11434
# Hosts that mean "listen everywhere" to the Ollama server; a client must
# connect to loopback instead.
_ANY_HOSTS = {"", "0.0.0.0", "::"}


def normalize_host(value: str) -> str:
    """Turn an OLLAMA_HOST value into a URL a client can connect to.

    Mirrors Ollama's own parsing: no scheme means http on port 11434; with an
    explicit scheme and no port, the scheme's default port is used.
    """
    value = value.strip()
    has_scheme = "://" in value
    parts = urlsplit(value if has_scheme else f"http://{value}")
    host = parts.hostname or ""
    if host in _ANY_HOSTS:
        host = "127.0.0.1"
    if ":" in host:
        host = f"[{host}]"  # IPv6 literal
    port = (
        parts.port if parts.port is not None else (None if has_scheme else DEFAULT_PORT)
    )
    netloc = f"{host}:{port}" if port is not None else host
    return f"{parts.scheme}://{netloc}{parts.path}".rstrip("/")


class OllamaError(Exception):
    pass


@dataclass
class PullProgress:
    status: str
    digest: str | None
    total: int | None
    completed: int | None


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        url = base_url or os.environ.get("OLLAMA_HOST") or DEFAULT_URL
        try:
            self._base_url = normalize_host(url)
        except ValueError:  # e.g. a non-numeric port in OLLAMA_HOST
            self._base_url = normalize_host(DEFAULT_URL)
        self._http = httpx.Client(base_url=self._base_url, timeout=30)

    def version(self) -> str | None:
        try:
            r = self._http.get("/api/version", timeout=1)
            r.raise_for_status()
            return r.json().get("version")
        except (httpx.HTTPError, ValueError):
            return None

    def list_models(self) -> list[str]:
        r = self._http.get("/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def pull(self, model: str) -> Iterator[PullProgress]:
        timeout = httpx.Timeout(10, read=None)
        with self._http.stream(
            "POST", "/api/pull", json={"model": model, "stream": True}, timeout=timeout
        ) as r:
            if r.is_error:
                r.read()  # so callers can show Ollama's error message
                r.raise_for_status()
            for line in r.iter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if "error" in data:
                    raise OllamaError(data["error"])
                yield PullProgress(
                    status=data.get("status", ""),
                    digest=data.get("digest"),
                    total=data.get("total"),
                    completed=data.get("completed"),
                )

    def chat(
        self,
        model: str,
        messages: list[dict],
        json_schema: dict | None = None,
        options: dict | None = None,
        think: bool | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if json_schema is not None:
            payload["format"] = json_schema
        if options is not None:
            payload["options"] = options
        if think is not None:
            payload["think"] = think
        r = self._http.post("/api/chat", json=payload, timeout=None)
        r.raise_for_status()
        return r.json()["message"]["content"]
