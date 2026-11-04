"""Provider registry."""

from __future__ import annotations

from .base import GeneratedImage, Provider, ProviderError
from .dryrun import DryRunProvider
from .gemini import GeminiProvider
from .openai_images import OpenAIImagesProvider
from .replicate_flux import ReplicateFluxProvider

REGISTRY: dict[str, type[Provider]] = {
    p.name: p
    for p in (DryRunProvider, OpenAIImagesProvider, GeminiProvider, ReplicateFluxProvider)
}


def get_provider(name: str, **options) -> Provider:
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise ProviderError(
            f"unknown provider {name!r} (available: {', '.join(sorted(REGISTRY))})"
        ) from None
    return cls(**options)


__all__ = ["REGISTRY", "get_provider", "Provider", "ProviderError", "GeneratedImage"]
