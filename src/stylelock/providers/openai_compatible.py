"""Any server that speaks OpenAI's Images API - a LiteLLM proxy, LocalAI, a self-hosted
gateway in front of a local model, or a vendor with an OpenAI-compatible endpoint.

Configuration (options come from `provider_defaults["openai-compatible"]`, `--option`, or env):
    base_url   STYLELOCK_COMPAT_BASE_URL   e.g. http://localhost:4000/v1     (required)
    model      STYLELOCK_MODEL                                              (required)
    key        STYLELOCK_COMPAT_API_KEY    some local servers accept any value
    edit       true to send reference images through /images/edits - only if the server has it

The server's capabilities are unknown to us, so the honest defaults are conservative: no
references, no transparency. Turn `edit` on once you have checked the endpoint supports it.
"""

from __future__ import annotations

import base64
import os

from ..prompt import PromptBundle
from .base import GeneratedImage, Provider, ProviderError


class OpenAICompatibleProvider(Provider):
    name = "openai-compatible"
    supports_reference_images = False
    supports_negative_prompt = False
    supports_transparency = False
    key_env = "STYLELOCK_COMPAT_API_KEY"
    default_model = ""
    notes = (
        "needs base_url (STYLELOCK_COMPAT_BASE_URL) and a model; set option edit=true to "
        "send references if the server implements /images/edits"
    )

    PASSTHROUGH = ("size", "quality", "background", "output_format", "response_format", "style")

    def __init__(self, **options):
        super().__init__(**options)
        # per instance: whether references can be sent depends on this server, not the class
        self.supports_reference_images = bool(options.get("edit"))

    @classmethod
    def describe(cls) -> dict:
        d = super().describe()
        d["key_set"] = bool(os.getenv(cls.key_env))
        d["base_url"] = os.getenv("STYLELOCK_COMPAT_BASE_URL", "")
        return d

    def generate(self, bundle: PromptBundle, n: int = 1) -> list[GeneratedImage]:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - depends on optional extra
            raise ProviderError("pip install 'stylelock[openai]' to use openai-compatible") from e

        base_url = self.options.get("base_url") or os.getenv("STYLELOCK_COMPAT_BASE_URL")
        if not base_url:
            raise ProviderError("openai-compatible needs base_url (or STYLELOCK_COMPAT_BASE_URL)")
        model = self.options.get("model")
        if not model:
            raise ProviderError("openai-compatible needs a model (STYLELOCK_MODEL or --option model=...)")

        client = OpenAI(base_url=base_url, api_key=os.getenv(self.key_env) or "not-needed")
        prompt = self.text_prompt(bundle)
        refs = self.reference_paths(bundle)
        params = {k: v for k, v in self.options.items() if k in self.PASSTHROUGH}

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
        for i, item in enumerate(resp.data or []):
            if getattr(item, "b64_json", None):
                data = base64.b64decode(item.b64_json)
            elif getattr(item, "url", None):
                data = _fetch(item.url)
            else:
                raise ProviderError("response item carried neither b64_json nor url")
            out.append(
                GeneratedImage(
                    data=data,
                    suffix="." + str(params.get("output_format", "png")),
                    provider_meta={
                        "provider": self.name,
                        "model": model,
                        "base_url": base_url,
                        "endpoint": "images.edit" if refs else "images.generate",
                        "index": i,
                        **params,
                    },
                )
            )
        if not out:
            raise ProviderError("the server returned no images")
        return out


def _fetch(url: str) -> bytes:
    from urllib.request import urlopen

    with urlopen(url, timeout=120) as r:  # noqa: S310 - URL returned by the configured server
        return r.read()
