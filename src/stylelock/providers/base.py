"""Provider interface. One adapter per image API; all of them take a PromptBundle."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..prompt import PromptBundle


class ProviderError(Exception):
    pass


@dataclass
class GeneratedImage:
    data: bytes
    suffix: str = ".png"
    provider_meta: dict = field(default_factory=dict)


class Provider:
    name: str = "base"
    supports_reference_images: bool = False
    supports_negative_prompt: bool = False

    def __init__(self, **options):
        self.options = options

    def generate(self, bundle: PromptBundle, n: int = 1) -> list[GeneratedImage]:
        raise NotImplementedError

    # -- helpers for adapters -------------------------------------------

    def text_prompt(self, bundle: PromptBundle) -> str:
        """Prompt text, with negatives folded in when the API has no negative field."""
        if self.supports_negative_prompt or not bundle.negative:
            return bundle.prompt
        return bundle.prompt + "\n\nAbsolutely avoid: " + ", ".join(bundle.negative) + "."

    def reference_paths(self, bundle: PromptBundle) -> list[str]:
        if not self.supports_reference_images:
            return []
        return [str(r.path) for r in bundle.references if r.path.exists()]
