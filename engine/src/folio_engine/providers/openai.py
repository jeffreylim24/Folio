import re

import httpx

from .base import (
    COMPLETE_TIMEOUT,
    LIST_TIMEOUT,
    Message,
    bad_shape,
    require_text,
    send,
)

DEFAULT_BASE = "https://api.openai.com/v1"
# OpenAI's /models also lists models that can't chat; hide those.
_NOT_CHAT = re.compile(
    r"embedding|tts|whisper|dall-e|moderation|image|audio|transcribe|realtime|search"
)
_PREFERRED = re.compile(r"gpt-|o\d")


def _chat_models(ids: list[str]) -> list[str]:
    chat = [i for i in ids if not _NOT_CHAT.search(i)]
    return sorted(chat, key=lambda i: (not _PREFERRED.match(i), i))


class OpenAIProvider:
    """OpenAI and any OpenAI-compatible server."""

    def __init__(
        self,
        api_key: str,
        model: str | None,
        base_url: str | None = None,
        chat_only: bool = False,
    ):
        """`chat_only` filters list_models to chat models (OpenAI itself only;
        compatible servers name their models freely)."""
        self._model = model
        self._chat_only = chat_only
        self._http = httpx.Client(
            base_url=(base_url or DEFAULT_BASE).rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def list_models(self) -> list[str]:
        data = send(self._http, "GET", "/models", LIST_TIMEOUT)
        try:
            ids = [m["id"] for m in data["data"]]
        except (KeyError, TypeError):
            raise bad_shape() from None
        return _chat_models(ids) if self._chat_only else ids

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
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise bad_shape() from None
        return require_text(text)
