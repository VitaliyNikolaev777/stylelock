"""OpenAI Images (gpt-image-1.5; gpt-image-1 was retired 2026-10-31).

Reference images are supported through the *edit* endpoint - when the bundle carries
references we call `images.edit` with them attached, otherwise `images.generate`.
There is no negative-prompt field, so negatives are folded into the text by the base class.
"""

from __future__ import annotations

import base64
import os

from ..prompt import PromptBundle
from .base import GeneratedImage, Provider, ProviderError


class OpenAIImagesProvider(Provider):
    name = "openai"
    supports_reference_images = True
    supports_negative_prompt = False
    supports_transparency = True
    key_env = "OPENAI_API_KEY"
    default_model = "gpt-image-1.5"
    notes = (
        "references go through images.edit. gpt-image-2 has no transparent background: "
        "render opaque onto flat #00FF00 and key it out (chroma_key.py)"
    )

    # `background: transparent` is what makes the icon/object types usable as
    # app assets - it requires png or webp output.
    PASSTHROUGH = ("size", "quality", "background", "output_format", "output_compression", "moderation")

    def generate(self, bundle: PromptBundle, n: int = 1) -> list[GeneratedImage]:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - depends on optional extra
            raise ProviderError("pip install 'stylelock[openai]' to use the openai provider") from e

        if not os.getenv("OPENAI_API_KEY"):
            raise ProviderError("OPENAI_API_KEY is not set (see .env.example)")

        client = OpenAI()
        model = self.options.get("model", self.default_model)
        prompt = self.text_prompt(bundle)
        refs = self.reference_paths(bundle)

        params = {k: v for k, v in self.options.items() if k in self.PASSTHROUGH}
        params.setdefault("size", "1536x1024")
        params.setdefault("quality", "high")
        if params.get("background") == "transparent":
            params.setdefault("output_format", "png")

        handles = []
        try:
            if refs:
                handles = [open(p, "rb") for p in refs]
                resp = client.images.edit(model=model, image=handles, prompt=prompt, n=n, **params)
            else:
                resp = client.images.generate(model=model, prompt=prompt, n=n, **params)
        finally:
            for h in handles:
                h.close()

        out = []
        for i, item in enumerate(resp.data):
            if not item.b64_json:
                raise ProviderError("response contained no image data")
            out.append(
                GeneratedImage(
                    data=base64.b64decode(item.b64_json),
                    suffix="." + params.get("output_format", "png"),
                    provider_meta={
                        "provider": self.name,
                        "model": model,
                        "endpoint": "images.edit" if refs else "images.generate",
                        "index": i,
                        **params,
                    },
                )
            )
        return out
