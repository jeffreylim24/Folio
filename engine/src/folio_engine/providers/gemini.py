import httpx

from .base import COMPLETE_TIMEOUT, LIST_TIMEOUT, Message, bad_shape, send

BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    def __init__(self, api_key: str, model: str | None):
        self._model = model
        self._http = httpx.Client(base_url=BASE, headers={"x-goog-api-key": api_key})

    def list_models(self) -> list[str]:
        data = send(self._http, "GET", "/models", LIST_TIMEOUT)
        try:
            return [
                m["name"].removeprefix("models/")
                for m in data["models"]
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
        except (KeyError, TypeError):
            raise bad_shape() from None

    def complete(self, messages: list[Message], json_schema: dict | None = None) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        payload: dict = {
            "contents": [
                {
                    "role": "model" if m["role"] == "assistant" else "user",
                    "parts": [{"text": m["content"]}],
                }
                for m in messages
                if m["role"] != "system"
            ]
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if json_schema is not None:
            payload["generationConfig"] = {
                "responseMimeType": "application/json",
                "responseSchema": json_schema,
            }
        data = send(
            self._http,
            "POST",
            f"/models/{self._model}:generateContent",
            COMPLETE_TIMEOUT,
            json=payload,
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            raise bad_shape() from None
