import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_URL = "http://127.0.0.1:11434"


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
        if "://" not in url:
            url = f"http://{url}"
        self._base_url = url.rstrip("/")
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
        self, model: str, messages: list[dict], json_schema: dict | None = None
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if json_schema is not None:
            payload["format"] = json_schema
        r = self._http.post("/api/chat", json=payload, timeout=None)
        r.raise_for_status()
        return r.json()["message"]["content"]
