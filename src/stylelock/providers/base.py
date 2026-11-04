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
    # whether the API can return an alpha channel; per-model exceptions go in `notes`
    supports_transparency: bool = False
    # env var holding the API key, or None when no key is needed
    key_env: str | None = None
    default_model: str = ""
    notes: str = ""

    def __init__(self, **options):
        self.options = options

    @classmethod
    def describe(cls) -> dict:
        """What this provider can do - for settings screens and for the agent's planning."""
        import os

        return {
            "name": cls.name,
            "default_model": cls.default_model,
            "key_env": cls.key_env,
            "key_set": bool(os.getenv(cls.key_env)) if cls.key_env else True,
            "supports_reference_images": cls.supports_reference_images,
            "supports_negative_prompt": cls.supports_negative_prompt,
            "supports_transparency": cls.supports_transparency,
            "notes": cls.notes,
        }

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
