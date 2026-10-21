from typing import Any

import keyring
from keyring.errors import PasswordDeleteError

from .config import ProviderName

SERVICE = "Folio"


class SecretStore:
    """API keys live only in the OS keychain (service "Folio", user = provider)."""

    def __init__(self, backend: Any = None):
        self._backend = backend if backend is not None else keyring

    def set_api_key(self, provider: ProviderName, key: str) -> None:
        self._backend.set_password(SERVICE, provider, key)

    def get_api_key(self, provider: ProviderName) -> str | None:
        return self._backend.get_password(SERVICE, provider)

    def delete_api_key(self, provider: ProviderName) -> None:
        try:
            self._backend.delete_password(SERVICE, provider)
        except PasswordDeleteError:
            pass  # nothing stored
