import keyring
import pytest


@pytest.fixture(autouse=True)
def _memory_keyring(monkeypatch):
    """Never touch the real OS keychain in tests."""
    store: dict[tuple[str, str], str] = {}

    def get_password(service, user):
        return store.get((service, user))

    def set_password(service, user, password):
        store[(service, user)] = password

    def delete_password(service, user):
        if (service, user) not in store:
            raise keyring.errors.PasswordDeleteError("not found")
        del store[(service, user)]

    monkeypatch.setattr(keyring, "get_password", get_password)
    monkeypatch.setattr(keyring, "set_password", set_password)
    monkeypatch.setattr(keyring, "delete_password", delete_password)
