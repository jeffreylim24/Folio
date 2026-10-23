import httpx

from ..catalog import CONTEXT_TOKENS, find_model
from ..ollama.client import OllamaClient, OllamaError
from .base import (
    OUTPUT_RESERVE_TOKENS,
    Message,
    ProviderError,
    error_for_status,
    estimate_tokens,
    network_error,
    require_text,
)


def _map(exc: Exception) -> ProviderError:
    if isinstance(exc, httpx.HTTPStatusError):
        return error_for_status(exc.response)
    if isinstance(exc, httpx.ConnectError | httpx.TimeoutException):
        return network_error()
    detail = f" {exc}" if isinstance(exc, OllamaError) and str(exc) else ""
    return ProviderError(
        "other", f"Something went wrong talking to the provider.{detail}"
    )


class OllamaProvider:
    def __init__(self, client: OllamaClient, model: str | None):
        self._client = client
        self._model = model

    def list_models(self) -> list[str]:
        try:
            return self._client.list_models()
        except (httpx.HTTPError, OllamaError) as exc:
            raise _map(exc) from None

    def complete(self, messages: list[Message], json_schema: dict | None = None) -> str:
        entry = find_model(self._model or "")
        num_ctx = entry.context_tokens if entry else CONTEXT_TOKENS
        if estimate_tokens(messages) + OUTPUT_RESERVE_TOKENS > num_ctx:
            raise ProviderError(
                "too_long",
                "This is too much text for the AI to read at once. "
                "Try a shorter document.",
            )
        extra: dict = {}
        if entry is not None and entry.thinking:
            extra["think"] = False
        options = {"num_ctx": num_ctx, "temperature": 0.2, "presence_penalty": 0}
        try:
            text = self._client.chat(
                self._model or "",
                list(messages),
                json_schema,
                options=options,
                **extra,
            )
        except (httpx.HTTPError, OllamaError, KeyError, ValueError) as exc:
            raise _map(exc) from None
        return require_text(text)
