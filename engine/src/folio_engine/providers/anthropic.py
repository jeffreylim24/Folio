import json

import httpx

from .base import COMPLETE_TIMEOUT, LIST_TIMEOUT, Message, bad_shape, send

BASE = "https://api.anthropic.com/v1"


class AnthropicProvider:
    def __init__(self, api_key: str, model: str | None):
        self._model = model
        self._http = httpx.Client(
            base_url=BASE,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )

    def list_models(self) -> list[str]:
        data = send(self._http, "GET", "/models", LIST_TIMEOUT)
        try:
            return [m["id"] for m in data["data"]]
        except (KeyError, TypeError):
            raise bad_shape() from None

    def complete(self, messages: list[Message], json_schema: dict | None = None) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        payload: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": [m for m in messages if m["role"] != "system"],
        }
        if system:
            payload["system"] = system
        if json_schema is not None:
            payload["tools"] = [
                {
                    "name": "out",
                    "description": "Return the result.",
                    "input_schema": json_schema,
                }
            ]
            payload["tool_choice"] = {"type": "tool", "name": "out"}
        data = send(self._http, "POST", "/messages", COMPLETE_TIMEOUT, json=payload)
        try:
            blocks = data["content"]
            if json_schema is not None:
                tool = next(b for b in blocks if b["type"] == "tool_use")
                return json.dumps(tool["input"])
            return "".join(b["text"] for b in blocks if b["type"] == "text")
        except (KeyError, TypeError, StopIteration):
            raise bad_shape() from None
