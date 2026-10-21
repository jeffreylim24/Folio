import keyring
from keyring.errors import PasswordDeleteError

from folio_engine.secrets import SecretStore


class DictBackend:
    def __init__(self):
        self.data = {}

    def set_password(self, service, user, pw):
        self.data[(service, user)] = pw

    def get_password(self, service, user):
        return self.data.get((service, user))

    def delete_password(self, service, user):
        if (service, user) not in self.data:
            raise PasswordDeleteError("nope")
        del self.data[(service, user)]


def test_roundtrip_uses_folio_service():
    backend = DictBackend()
    s = SecretStore(backend)
    assert s.get_api_key("openai") is None
    s.set_api_key("openai", "sk-1")
    assert s.get_api_key("openai") == "sk-1"
    assert backend.data == {("Folio", "openai"): "sk-1"}


def test_delete_ignores_missing():
    s = SecretStore(DictBackend())
    s.delete_api_key("gemini")
    s.set_api_key("gemini", "k")
    s.delete_api_key("gemini")
    assert s.get_api_key("gemini") is None


def test_default_backend_is_keyring_module_patched_in_tests():
    s = SecretStore()
    s.set_api_key("anthropic", "k")
    assert keyring.get_password("Folio", "anthropic") == "k"
