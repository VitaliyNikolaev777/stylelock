"""No-network provider. Writes a placeholder PNG so the whole pipeline can be exercised
without an API key - used by the tests and by `stylelock generate --provider dryrun`."""

from __future__ import annotations

import struct
import zlib

from ..prompt import PromptBundle
from .base import GeneratedImage, Provider


class DryRunProvider(Provider):
    name = "dryrun"
    supports_reference_images = True
    supports_negative_prompt = True
    supports_transparency = True
    default_model = "placeholder"
    notes = "no network, no key: writes a 64px placeholder so the pipeline can be exercised"

    def generate(self, bundle: PromptBundle, n: int = 1) -> list[GeneratedImage]:
        return [
            GeneratedImage(
                data=_solid_png(64, 64),
                provider_meta={
                    "provider": self.name,
                    "note": "placeholder image - no API was called",
                    "prompt_chars": len(self.text_prompt(bundle)),
                    "references": [r.id for r in bundle.references],
                    "index": i,
                },
            )
            for i in range(n)
        ]


def _solid_png(width: int, height: int, rgb: tuple[int, int, int] = (18, 22, 31)) -> bytes:
    """Minimal valid PNG, stdlib only."""
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
