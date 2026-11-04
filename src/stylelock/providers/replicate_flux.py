"""Replicate (Flux family).

This is the provider to use if you go the LoRA route: point `model` at a
`flux-dev-lora` style endpoint and pass `lora_weights` in `provider_defaults.replicate`,
and the trained style adapter does the heavy lifting instead of the text spec.
"""

from __future__ import annotations

import os

from ..prompt import PromptBundle
from .base import GeneratedImage, Provider, ProviderError


class ReplicateFluxProvider(Provider):
    name = "replicate"
    supports_reference_images = False  # true only on img2img / redux endpoints
    supports_negative_prompt = False   # flux ignores it; folded into text instead
    supports_transparency = False
    key_env = "REPLICATE_API_TOKEN"
    default_model = "black-forest-labs/flux-1.1-pro"
    notes = "any Replicate model id works; LoRA via lora_weights in provider_defaults"

    PASSTHROUGH = (
        "aspect_ratio", "output_format", "output_quality", "seed", "guidance",
        "num_inference_steps", "lora_weights", "lora_scale", "megapixels",
        "prompt_strength", "image", "image_prompt",
    )

    def generate(self, bundle: PromptBundle, n: int = 1) -> list[GeneratedImage]:
        try:
            import replicate
        except ImportError as e:  # pragma: no cover - depends on optional extra
            raise ProviderError("pip install 'stylelock[replicate]' to use the replicate provider") from e

        if not os.getenv("REPLICATE_API_TOKEN"):
            raise ProviderError("REPLICATE_API_TOKEN is not set (see .env.example)")

        model = self.options.get("model", self.default_model)
        payload = {"prompt": self.text_prompt(bundle), "num_outputs": n}
        payload.update({k: v for k, v in self.options.items() if k in self.PASSTHROUGH})

        result = replicate.run(model, input=payload)
        items = result if isinstance(result, list) else [result]

        out = []
        for i, item in enumerate(items):
            data = item.read() if hasattr(item, "read") else _fetch(str(item))
            fmt = self.options.get("output_format", "png")
            out.append(
                GeneratedImage(
                    data=data,
                    suffix=f".{fmt}",
                    provider_meta={"provider": self.name, "model": model, "input": payload, "index": i},
                )
            )
        return out


def _fetch(url: str) -> bytes:
    from urllib.request import urlopen

    with urlopen(url) as r:  # noqa: S310 - replicate-controlled URL
        return r.read()
