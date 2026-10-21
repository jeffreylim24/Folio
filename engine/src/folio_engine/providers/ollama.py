import httpx

from ..ollama.client import OllamaClient, OllamaError
from .base import Message, ProviderError, error_for_status, network_error


def _map(exc: Exception) -> ProviderError:
    if isinstance(exc, httpx.HTTPStatusError):
        return error_for_status(exc.response)
    if isinstance(exc, httpx.ConnectError | httpx.TimeoutException):
        return network_error()
    detail = f" {exc}" if isinstance(exc, OllamaError) and str(exc) else ""
    return ProviderError("other", f"Something went wrong talking to Ollama.{detail}")


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
        try:
            return self._client.chat(self._model or "", list(messages), json_schema)
        except (httpx.HTTPError, OllamaError, KeyError, ValueError) as exc:
            raise _map(exc) from None
