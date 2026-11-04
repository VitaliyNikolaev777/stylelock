"""Google Gemini image generation (google-genai SDK).

Reference images ride along as inline image parts in the same request as the prompt.
Model name comes from `provider_defaults.gemini.model` in the style guide so you can
move to a newer image model without touching this file.
"""

from __future__ import annotations

import mimetypes
import os

from ..prompt import PromptBundle
from .base import GeneratedImage, Provider, ProviderError


class GeminiProvider(Provider):
    name = "gemini"
    supports_reference_images = True
    supports_negative_prompt = False
    supports_transparency = False
    key_env = "GEMINI_API_KEY"
    default_model = "gemini-3-pro-image"
    notes = "also reads GOOGLE_API_KEY; one image per call; no alpha channel"

    @classmethod
    def describe(cls) -> dict:
        import os

        d = super().describe()
        d["key_set"] = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        return d

    def generate(self, bundle: PromptBundle, n: int = 1) -> list[GeneratedImage]:
        try:
            from google import genai
            from google.genai import types
        except ImportError as e:  # pragma: no cover - depends on optional extra
            raise ProviderError("pip install 'stylelock[gemini]' to use the gemini provider") from e

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ProviderError("GEMINI_API_KEY is not set (see .env.example)")

        client = genai.Client(api_key=api_key)
        model = self.options.get("model", self.default_model)

        parts: list = [self.text_prompt(bundle)]
        for path in self.reference_paths(bundle):
            mime = mimetypes.guess_type(path)[0] or "image/png"
            with open(path, "rb") as fh:
                parts.append(types.Part.from_bytes(data=fh.read(), mime_type=mime))

        images: list[GeneratedImage] = []
        for call in range(n):  # the API returns one image per call
            resp = client.models.generate_content(model=model, contents=parts)
            for cand in resp.candidates or []:
                for part in cand.content.parts or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and inline.data:
                        suffix = mimetypes.guess_extension(inline.mime_type or "image/png") or ".png"
                        images.append(
                            GeneratedImage(
                                data=inline.data,
                                suffix=".jpg" if suffix == ".jpe" else suffix,
                                provider_meta={"provider": self.name, "model": model, "index": call},
                            )
                        )
        if not images:
            raise ProviderError("Gemini returned no image parts (often a safety block - check the text response)")
        return images
