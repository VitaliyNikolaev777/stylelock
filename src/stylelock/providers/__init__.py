"""Provider registry."""

from __future__ import annotations

from .base import GeneratedImage, Provider, ProviderError
from .dryrun import DryRunProvider
from .gemini import GeminiProvider
from .openai_compatible import OpenAICompatibleProvider
from .openai_images import OpenAIImagesProvider
from .replicate_flux import ReplicateFluxProvider

REGISTRY: dict[str, type[Provider]] = {
    p.name: p
    for p in (
        DryRunProvider, OpenAIImagesProvider, OpenAICompatibleProvider,
        GeminiProvider, ReplicateFluxProvider,
    )
}


def get_provider(name: str, **options) -> Provider:
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise ProviderError(
            f"unknown provider {name!r} (available: {', '.join(sorted(REGISTRY))})"
        ) from None
    return cls(**options)


def describe_all() -> list[dict]:
    return [REGISTRY[name].describe() for name in sorted(REGISTRY)]


__all__ = ["REGISTRY", "describe_all", "get_provider", "Provider", "ProviderError", "GeneratedImage"]
