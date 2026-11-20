"""
Perchance Image Generator - Standalone Core

Pure Python implementation for generating images via Perchance's free API.
No Hermes or other framework dependencies.

Usage (standalone):
    from perchance_image_gen.core import PerchanceGenerator

    gen = PerchanceGenerator()
    result = gen.generate("a cat in a hat", aspect_ratio="square")
    if result["success"]:
        print(result["image_path"])

Key management:
    - PERCHANCE_USER_KEY env var
    - ~/.config/perchance/user_key.txt (or custom cache_dir)
    - Automatic caching of working keys
    - Auto-fetch with Playwright (optional)

Requires: requests (playwright optional for auto key fetch)
"""

from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

PERCHANCE_CREATE_URL = "https://image-generation.perchance.org/api/generate"
PERCHANCE_DOWNLOAD_URL = "https://image-generation.perchance.org/api/downloadTemporaryImage"

DEFAULT_RESOLUTIONS = {
    "landscape": "1536x1024",
    "square": "1024x1024",
    "portrait": "1024x1536",
}

DEFAULT_CACHE_DIR = Path.home() / ".config" / "perchance"
DEFAULT_KEY_FILE = DEFAULT_CACHE_DIR / "user_key.txt"


class PerchanceGenerator:
    """Standalone Perchance text-to-image generator."""

    def __init__(
        self,
        user_key: Optional[str] = None,
        cache_dir: Optional[Path | str] = None,
        auto_fetch: bool = True,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.key_file = self.cache_dir / "user_key.txt"
        self.auto_fetch = auto_fetch
        self.user_key = user_key or self._get_user_key()

    def _get_user_key(self) -> Optional[str]:
        # Priority: explicit (if already set) → env → cache
        if getattr(self, "user_key", None):
            return self.user_key

        env_key = os.environ.get("PERCHANCE_USER_KEY", "").strip()
        if env_key and len(env_key) == 64:
            return env_key

        try:
            if self.key_file.exists():
                key = self.key_file.read_text().strip()
                if len(key) == 64 and all(c in "0123456789abcdefABCDEF" for c in key):
                    return key
        except Exception:
            pass
        return None

    def _save_key(self, key: str) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.key_file.write_text(key.strip())
            logger.debug("Cached Perchance key")
        except Exception as exc:
            logger.debug("Could not cache key: %s", exc)

    def _validate_key(self, key: str) -> bool:
        if not key or len(key) != 64:
            return False
        try:
            r = requests.get(
                "https://image-generation.perchance.org/api/checkVerificationStatus",
                params={"userKey": key, "__cacheBust": str(random.random())},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            return "not_verified" not in r.text.lower() and r.status_code == 200
        except Exception:
            return False  # assume ok if we can't check

    def fetch_key(self, headless: bool = True, browser: str = "chromium") -> Optional[str]:
        """Attempt to fetch a fresh userKey using Playwright if available."""
        from .key_fetcher import fetch_key_with_playwright  # lazy import

        key = fetch_key_with_playwright(headless=headless, browser=browser)
        if key:
            self._save_key(key)
            self.user_key = key
            return key
        return None

    def _ensure_key(self) -> Optional[str]:
        if self.user_key and self._validate_key(self.user_key):
            return self.user_key

        if self.auto_fetch:
            new_key = self.fetch_key()
            if new_key:
                return new_key

        # fall back to whatever we have
        return self.user_key

    def generate(
        self,
        prompt: str,
        *,
        aspect_ratio: str = "landscape",
        guidance_scale: float = 7.0,
        negative_prompt: str = "nudity, text, watermark, low quality",
        seed: str = "-1",
        resolution: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate an image.

        Returns dict with:
            success: bool
            image: str (path) or None
            error: str or None
            prompt, etc.
        """
        if not prompt or not isinstance(prompt, str):
            return {"success": False, "error": "Prompt is required", "prompt": prompt}

        user_key = self._ensure_key()
        if not user_key:
            return {
                "success": False,
                "error": "No valid Perchance userKey. Run `perchance-key-fetch` or set PERCHANCE_USER_KEY.",
                "prompt": prompt,
            }

        if resolution is None:
            resolution = DEFAULT_RESOLUTIONS.get(aspect_ratio, "1024x1024")

        try:
            params = {
                "prompt": quote(prompt),
                "negativePrompt": quote(negative_prompt),
                "userKey": user_key,
                "__cache_bust": str(random.random()),
                "seed": str(seed),
                "resolution": resolution,
                "guidanceScale": str(guidance_scale),
                "channel": "ai-text-to-image-generator",
                "subChannel": "public",
                "requestId": str(random.random()),
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://perchance.org/ai-text-to-image-generator",
            }

            create_resp = requests.get(PERCHANCE_CREATE_URL, params=params, timeout=60, headers=headers)

            if create_resp.status_code == 403 or "Just a moment" in create_resp.text:
                return {"success": False, "error": "Cloudflare block. Try fetching a fresh key in a browser."}

            if "invalid_key" in create_resp.text.lower():
                # Invalidate and try one auto refresh
                try:
                    if self.key_file.exists():
                        self.key_file.unlink()
                except Exception:
                    pass
                new_key = self.fetch_key() if self.auto_fetch else None
                if new_key:
                    return {"success": False, "error": "Key was invalid. A fresh one was fetched — please retry."}
                return {"success": False, "error": "Invalid or expired userKey."}

            data = create_resp.json()
            image_id = data.get("imageId")
            if not image_id:
                return {"success": False, "error": f"Unexpected response: {create_resp.text[:200]}"}

            dl_resp = requests.get(
                PERCHANCE_DOWNLOAD_URL,
                params={"imageId": image_id},
                timeout=60,
                headers=headers,
            )
            dl_resp.raise_for_status()

            if len(dl_resp.content) < 1000:
                return {"success": False, "error": "Received empty/small image file."}

            # Save
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            filename = f"perchance_{int(time.time())}_{image_id[:8]}.jpg"
            image_path = self.cache_dir / filename
            image_path.write_bytes(dl_resp.content)

            self._save_key(user_key)  # mark as good

            return {
                "success": True,
                "image": str(image_path),
                "image_id": image_id,
                "prompt": prompt,
                "resolution": resolution,
                "guidance_scale": guidance_scale,
            }

        except Exception as exc:
            logger.exception("Perchance generation failed")
            return {"success": False, "error": str(exc), "prompt": prompt}


# Convenience function
def generate_image(prompt: str, **kwargs) -> Dict[str, Any]:
    """Quick one-shot generation."""
    gen = PerchanceGenerator()
    return gen.generate(prompt, **kwargs)
