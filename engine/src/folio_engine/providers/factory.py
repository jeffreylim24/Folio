from ..config import Settings
from ..ollama.client import OllamaClient
from ..secrets import SecretStore
from .anthropic import AnthropicProvider
from .base import Provider, ProviderError
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider


def make_provider(
    settings: Settings,
    secrets: SecretStore,
    api_key: str | None = None,
    ollama_client: OllamaClient | None = None,
) -> Provider:
    """Build the provider for `settings`. `api_key` overrides the stored key
    (used to verify a key before it is saved)."""
    name = settings.provider
    if name is None:
        raise ProviderError("other", "No provider has been chosen yet.")
    if name == "ollama":
        return OllamaProvider(ollama_client or OllamaClient(), settings.model)
    key = api_key or secrets.get_api_key(name)
    if not key:
        raise ProviderError("auth", "No API key is saved for this provider.")
    if name == "anthropic":
        return AnthropicProvider(key, settings.model)
    if name == "gemini":
        return GeminiProvider(key, settings.model)
    return OpenAIProvider(
        key, settings.model, settings.base_url if name == "openai_compatible" else None
    )
