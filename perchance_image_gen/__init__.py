"""
perchance_image_gen

Standalone Perchance text-to-image generator for any terminal / Python script.

Quick start:
    from perchance_image_gen import PerchanceGenerator, generate_image

    result = generate_image("a beautiful landscape")
    print(result["image"])

CLI (after pip install):
    perchance-gen "your prompt here"
    perchance-key-fetch
"""

from .core import PerchanceGenerator, generate_image
from .key_fetcher import fetch_key_with_playwright

__version__ = "0.2.0"
__all__ = ["PerchanceGenerator", "generate_image", "fetch_key_with_playwright"]
