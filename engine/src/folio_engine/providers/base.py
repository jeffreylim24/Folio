import math
from collections.abc import Callable
from typing import Any, Literal, Protocol, TypedDict

import httpx

ErrorKind = Literal["auth", "network", "rate_limit", "too_long", "other"]

OUTPUT_RESERVE_TOKENS = 2048
LIST_TIMEOUT = 15
COMPLETE_TIMEOUT = 60

_MESSAGES = {
    "auth": "That API key was rejected. Check it and try again.",
    "network": (
        "Couldn't reach the provider. Check your internet connection and try again."
    ),
    "rate_limit": "The provider is rate-limiting requests. Wait a minute and try again.",
}


class Message(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


def estimate_tokens(messages: list[Message]) -> int:
    """Rough token count: about 3.5 characters per token."""
    return math.ceil(sum(len(m["content"]) for m in messages) / 3.5)


class ProviderError(Exception):
    def __init__(self, kind: ErrorKind, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


class Provider(Protocol):
    def list_models(self) -> list[str]: ...

    def complete(
        self, messages: list[Message], json_schema: dict | None = None
    ) -> str: ...


def _detail(response: httpx.Response) -> str | None:
    """Short provider-supplied error text, if any. Never contains request data."""
    try:
        err = response.json().get("error")
    except (ValueError, AttributeError):
        return None
    if isinstance(err, dict):
        err = err.get("message")
    if isinstance(err, str) and err.strip():
        return err.strip()[:200]
    return None


def error_for_status(
    response: httpx.Response, invalid_key: bool = False
) -> ProviderError:
    code = response.status_code
    if invalid_key or code in (401, 403):
        return ProviderError("auth", _MESSAGES["auth"])
    if code == 429:
        return ProviderError("rate_limit", _MESSAGES["rate_limit"])
    message = "Something went wrong talking to the provider."
    detail = _detail(response)
    if detail:
        message = f"{message} {detail}"
    return ProviderError("other", message)


def network_error() -> ProviderError:
    return ProviderError("network", _MESSAGES["network"])


def send(
    http: httpx.Client,
    method: str,
    url: str,
    timeout: float,
    is_invalid_key: Callable[[httpx.Response], bool] | None = None,
    **kwargs: Any,
) -> Any:
    """Perform a request and return parsed JSON, mapping failures to ProviderError."""
    try:
        r = http.request(method, url, timeout=timeout, **kwargs)
    except (httpx.ConnectError, httpx.TimeoutException):
        raise network_error() from None
    except httpx.HTTPError:
        raise ProviderError(
            "other", "Something went wrong talking to the provider."
        ) from None
    if r.status_code >= 400:
        raise error_for_status(r, bool(is_invalid_key and is_invalid_key(r)))
    try:
        return r.json()
    except ValueError:
        raise ProviderError(
            "other", "The provider sent a response Folio couldn't read."
        ) from None


def bad_shape() -> ProviderError:
    return ProviderError("other", "The provider sent a response Folio couldn't read.")


def require_text(text: object) -> str:
    """A completion must contain some text; an empty reply is an error."""
    if not isinstance(text, str) or not text.strip():
        raise ProviderError(
            "other",
            "The model sent an empty reply. Try again, or choose a different model.",
        )
    return text
