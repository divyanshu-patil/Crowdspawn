"""Picks the LLM provider from settings. The only module that names concrete adapters."""

import logging

from ..settings import Settings
from .base import LLMError, LLMProvider
from .fake import FakeProvider
from .gemini import GeminiProvider
from .ollama_cloud import OllamaCloudProvider
from .openai_compat import OpenAICompatProvider

log = logging.getLogger(__name__)


def build_provider(s: Settings) -> LLMProvider | None:
    """Return the configured provider, or None if it is unconfigured (brief uses the template)."""
    try:
        match s.llm_provider:
            case "ollama_cloud":
                return OllamaCloudProvider(
                    s.ollama_base_url, s.ollama_api_key.get_secret_value(), s.ollama_model
                )
            case "gemini":
                return GeminiProvider(s.gemini_api_key.get_secret_value(), s.gemini_model)
            case "openai_compat":
                return OpenAICompatProvider(
                    s.openai_compat_base_url,
                    s.openai_compat_api_key.get_secret_value(),
                    s.openai_compat_model,
                )
            case "fake":
                if s.app_env == "production":
                    raise LLMError("LLM_PROVIDER=fake is not allowed in production")
                return FakeProvider()
            case other:
                raise LLMError(f"Unknown LLM_PROVIDER {other!r}")
    except LLMError as e:
        log.warning("LLM provider unavailable: %s", e.detail)
        return None


def model_name(s: Settings) -> str:
    return {
        "ollama_cloud": s.ollama_model,
        "gemini": s.gemini_model,
        "openai_compat": s.openai_compat_model,
        "fake": "fake-1",
    }.get(s.llm_provider, "")
