"""stylelock - style-locked image generation.

Public surface:
    from stylelock import generate_image, StyleGuide, Library, assemble

`generate_image` is `stylelock.generate.run` - the wrapper every image goes through.
(The alias exists so this name does not shadow the `stylelock.generate` module.)
"""

from .generate import run as generate_image
from .manifest import Library
from .prompt import assemble
from .style import StyleGuide

__version__ = "0.2.0"
__all__ = ["generate_image", "StyleGuide", "Library", "assemble", "__version__"]
