from __future__ import annotations

from ..config import ParticipantConfig
from .anthropic import AnthropicProvider
from .base import ProviderAdapter
from .codex import CodexCliProvider
from .fake import FakeProvider
from .google import GoogleProvider
from .openai_compatible import OpenAICompatibleProvider


def build_provider(config: ParticipantConfig, *, timeout_seconds: int) -> ProviderAdapter:
    providers: dict[str, type[ProviderAdapter]] = {
        "codex-cli": CodexCliProvider,
        "anthropic": AnthropicProvider,
        "google": GoogleProvider,
        "openai-compatible": OpenAICompatibleProvider,
        "fake": FakeProvider,
    }
    return providers[config.transport](config, timeout_seconds=timeout_seconds)
