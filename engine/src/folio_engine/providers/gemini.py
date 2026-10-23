import httpx

from .base import (
    COMPLETE_TIMEOUT,
    LIST_TIMEOUT,
    Message,
    bad_shape,
    require_text,
    send,
)

BASE = "https://generativelanguage.googleapis.com/v1beta"


def _invalid_key(response: httpx.Response) -> bool:
    """Gemini reports a bad key as HTTP 400 rather than 401."""
    if response.status_code != 400:
        return False
    try:
        err = response.json()["error"]
    except (ValueError, KeyError, TypeError):
        return False
    if not isinstance(err, dict):
        return False
    details = err.get("details")
    if isinstance(details, list) and any(
        isinstance(d, dict) and d.get("reason") == "API_KEY_INVALID" for d in details
    ):
        return True
    return "API key" in str(err.get("message", ""))


class GeminiProvider:
    def __init__(self, api_key: str, model: str | None):
        self._model = model
        self._http = httpx.Client(base_url=BASE, headers={"x-goog-api-key": api_key})

    def list_models(self) -> list[str]:
        data = send(
            self._http, "GET", "/models", LIST_TIMEOUT, is_invalid_key=_invalid_key
        )
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
            is_invalid_key=_invalid_key,
            json=payload,
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError, AttributeError):
            raise bad_shape() from None
        return require_text(text)
