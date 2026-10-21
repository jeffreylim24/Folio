import httpx

from .base import COMPLETE_TIMEOUT, LIST_TIMEOUT, Message, bad_shape, send

DEFAULT_BASE = "https://api.openai.com/v1"


class OpenAIProvider:
    """OpenAI and any OpenAI-compatible server."""

    def __init__(self, api_key: str, model: str | None, base_url: str | None = None):
        self._model = model
        self._http = httpx.Client(
            base_url=(base_url or DEFAULT_BASE).rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def list_models(self) -> list[str]:
        data = send(self._http, "GET", "/models", LIST_TIMEOUT)
        try:
            return [m["id"] for m in data["data"]]
        except (KeyError, TypeError):
            raise bad_shape() from None

    def complete(self, messages: list[Message], json_schema: dict | None = None) -> str:
        payload: dict = {"model": self._model, "messages": messages}
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "out", "schema": json_schema, "strict": True},
            }
        data = send(
            self._http, "POST", "/chat/completions", COMPLETE_TIMEOUT, json=payload
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise bad_shape() from None
