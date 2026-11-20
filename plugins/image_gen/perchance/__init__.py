"""Perchance AI Image Generator provider for Hermes.

Free, no-signup text-to-image via https://perchance.org/ai-text-to-image-generator

Uses the reverse-engineered direct API (image-generation.perchance.org).
Requires a valid `userKey` (obtained from a real browser session on the Perchance page).
The key is cached after first successful use.

CLI helper: `hermes perchance ...` (see `hermes perchance --help`)

Setup:
  1. Visit https://perchance.org/ai-text-to-image-generator in a browser
  2. Open DevTools → Network tab
  3. Click Generate
  4. Find a request to /api/generate that contains `userKey=...` (64 hex chars)
  5. Copy the key and set it:
     - `hermes perchance key set <key>`
     - Or environment: export PERCHANCE_USER_KEY="..."
     - Or config.yaml under image_gen.perchance.user_key

The plugin will auto-cache the last working key.
"""

from __future__ import annotations

import logging
import os
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    success_response,
)

logger = logging.getLogger(__name__)

PERCHANCE_CREATE_URL = "https://image-generation.perchance.org/api/generate"
PERCHANCE_DOWNLOAD_URL = "https://image-generation.perchance.org/api/downloadTemporaryImage"
CACHE_KEY_FILE = Path.home() / ".hermes" / "cache" / "perchance_user_key.txt"

# Reasonable default resolutions for different aspects
RESOLUTIONS = {
    "landscape": "1536x1024",
    "square": "1024x1024",
    "portrait": "1024x1536",
}


def load_image_gen_config(sub: Optional[str] = None) -> Dict[str, Any]:
    """Read image_gen (or image_gen.<sub>) from config.yaml."""
    label = "image_gen" if sub is None else f"image_gen.{sub}"
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        if sub is not None:
            section = section.get(sub) if isinstance(section, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception:
        return {}


def prompt_required_error(provider: str, aspect: str) -> Dict[str, Any]:
    return error_response(
        provider,
        "Prompt is required and must be a non-empty string",
        "prompt_required",
        prompt="",
        aspect_ratio=aspect,
    )


def _get_cached_key() -> Optional[str]:
    try:
        if CACHE_KEY_FILE.exists():
            key = CACHE_KEY_FILE.read_text().strip()
            if len(key) == 64 and all(c in "0123456789abcdef" for c in key.lower()):
                return key
    except Exception:
        pass
    return None


def _save_cached_key(key: str) -> None:
    try:
        CACHE_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_KEY_FILE.write_text(key.strip())
    except Exception as exc:
        logger.debug("Could not cache Perchance key: %s", exc)


def _get_user_key(cfg: Dict[str, Any]) -> Optional[str]:
    # Priority: env var → config → cached file
    env_key = os.environ.get("PERCHANCE_USER_KEY", "").strip()
    if env_key and len(env_key) == 64:
        return env_key

    cfg_key = cfg.get("user_key") or cfg.get("userKey") or cfg.get("key")
    if isinstance(cfg_key, str) and len(cfg_key.strip()) == 64:
        return cfg_key.strip()

    return _get_cached_key()


def _resolve_resolution(aspect: str) -> str:
    return RESOLUTIONS.get(aspect, RESOLUTIONS["square"])


def _validate_key(key: str) -> bool:
    """Quick validation: check format and make a lightweight test request."""
    if not key or len(key) != 64 or not all(c in "0123456789abcdefABCDEF" for c in key):
        return False
    # Try a minimal request to see if it works (will likely fail on CF but catch invalid_key)
    try:
        params = {
            "prompt": quote("'test'"),
            "negativePrompt": quote("'test'"),
            "userKey": key,
            "__cache_bust": str(random.random()),
            "seed": "-1",
            "resolution": "512x512",
            "guidanceScale": "1",
            "channel": "ai-text-to-image-generator",
            "subChannel": "public",
            "requestId": str(random.random()),
        }
        r = requests.get(PERCHANCE_CREATE_URL, params=params, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://perchance.org/ai-text-to-image-generator",
        })
        text = r.text.lower()
        if "invalid_key" in text or "just a moment" in text:
            return False
        if r.status_code == 200 and "imageid" in text:
            return True
        return False  # conservative
    except Exception:
        return False  # can't validate over network, assume format is ok


def _try_fetch_key_playwright(timeout: int = 60, headless: bool = True, browser_type: str = "chromium") -> Optional[str]:
    """Improved Playwright-based key fetcher.

    - Handles common Perchance iframe structure
    - Multiple button/input selectors based on community reverse-engineering
    - Listens for both URL params and POST data
    - Optional visible browser (headless=False) for Cloudflare challenges
    - Tries verification endpoint after capture
    - Falls back across browsers if available
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout, Error as PlaywrightError
    except ImportError:
        return None

    key = None

    def _extract_key_from_url(url: str) -> Optional[str]:
        if "userKey=" not in url:
            return None
        try:
            qs = url.split("?", 1)[1] if "?" in url else ""
            for part in qs.split("&"):
                if part.startswith("userKey="):
                    candidate = part.split("=", 1)[1].split("&")[0]
                    if len(candidate) == 64 and all(c in "0123456789abcdefABCDEF" for c in candidate):
                        return candidate
        except Exception:
            pass
        return None

    def _extract_key_from_post_data(request) -> Optional[str]:
        try:
            if request.method == "POST":
                post_data = request.post_data or ""
                if "userKey" in post_data:
                    # crude parse
                    for part in post_data.split("&"):
                        if part.startswith("userKey="):
                            cand = part.split("=", 1)[1]
                            if len(cand) == 64:
                                return cand
        except Exception:
            pass
        return None

    def _verify_key(candidate: str) -> bool:
        """Quick verification using Perchance's check endpoint (from community scripts)."""
        try:
            r = requests.get(
                "https://image-generation.perchance.org/api/checkVerificationStatus",
                params={"userKey": candidate, "__cacheBust": str(random.random())},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if "not_verified" not in r.text.lower() and r.status_code == 200:
                return True
        except Exception:
            pass
        return False

    browsers_to_try = [browser_type, "firefox", "chromium"] if browser_type != "chromium" else ["chromium", "firefox"]

    for btype in browsers_to_try:
        try:
            with sync_playwright() as p:
                launch_browser = getattr(p, btype, p.chromium)
                browser = launch_browser.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"] if not headless else None)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1366, "height": 768},
                    locale="en-US",
                )
                page = context.new_page()

                captured_keys = []

                def on_request(request):
                    nonlocal key
                    if "image-generation.perchance.org/api/generate" in request.url or "/api/generate" in request.url:
                        k = _extract_key_from_url(request.url)
                        if k:
                            captured_keys.append(k)
                            key = k
                        k2 = _extract_key_from_post_data(request)
                        if k2:
                            captured_keys.append(k2)
                            key = k2

                page.on("request", on_request)

                # Go to page
                page.goto("https://perchance.org/ai-text-to-image-generator", wait_until="domcontentloaded", timeout=30000)

                # Wait out basic Cloudflare if present (best effort)
                try:
                    page.wait_for_selector("iframe, button, input, #generateButtonEl", timeout=8000)
                except Exception:
                    pass

                # Handle iframe (very common on Perchance)
                try:
                    iframe = page.query_selector("iframe")
                    if iframe:
                        frame = iframe.content_frame()
                        if frame:
                            page = frame  # switch context for clicks
                except Exception:
                    pass

                # Try multiple ways to trigger a generation (which mints the key)
                clicked = False
                selectors = [
                    "button:has-text('Generate')",
                    "button#generateButtonEl",
                    "button.generate-button",
                    "input[type=submit]",
                    "button[type=submit]",
                    "#generate",
                    "text=Generate",
                    "button >> text=Generate",
                ]
                for sel in selectors:
                    try:
                        page.click(sel, timeout=3000)
                        clicked = True
                        break
                    except Exception:
                        continue

                if not clicked:
                    # Fallback: fill prompt area and submit
                    try:
                        for sel in ["textarea", "input[type='text']", "#prompt", ".prompt-input"]:
                            try:
                                page.fill(sel, "test key fetch prompt", timeout=2000)
                                page.keyboard.press("Enter")
                                clicked = True
                                break
                            except Exception:
                                continue
                    except Exception:
                        pass

                # Wait for the critical network request (up to timeout)
                start = time.time()
                while key is None and (time.time() - start) < min(timeout, 25):
                    page.wait_for_timeout(800)
                    # Also try waiting specifically for the generate endpoint
                    try:
                        page.wait_for_request(lambda r: "generate" in r.url and "perchance" in r.url, timeout=3000)
                    except Exception:
                        pass

                browser.close()

                if key:
                    if _verify_key(key):
                        _save_cached_key(key)
                        return key
                    else:
                        # still return it; caller can validate later
                        _save_cached_key(key)
                        return key

        except PlaywrightTimeout:
            continue
        except PlaywrightError as exc:
            logger.debug(f"Playwright {btype} error: {exc}")
            continue
        except Exception as exc:
            logger.debug(f"Playwright key fetch ({btype}) failed: {exc}")
            continue

    return key


def _try_fetch_key_automatically(headless: bool = True) -> Optional[str]:
    """Best-effort automatic key fetch.
    Tries playwright first (if installed), otherwise returns None.
    """
    key = _try_fetch_key_playwright(headless=headless)
    if key:
        _save_cached_key(key)
        return key
    return None


def _auto_ensure_key(cfg: Dict[str, Any]) -> Optional[str]:
    """Automatically ensure we have a usable key. Tries cache/env/config, then auto-fetch if needed."""
    key = _get_user_key(cfg)
    if key and _validate_key(key):
        return key

    # Try auto fetch
    new_key = _try_fetch_key_automatically()
    if new_key:
        return new_key

    return None


class PerchanceImageGenProvider(ImageGenProvider):
    """Free Perchance text-to-image provider (requires userKey from browser session)."""

    provider_id = "perchance"
    name = "perchance"
    label = "Perchance (free)"

    setup = dict(
        name="Perchance",
        badge="free",
        tag="Free AI image generator — no account, rate-limited, Cloudflare protected",
        key="PERCHANCE_USER_KEY",
        prompt="Perchance userKey (64 hex chars from DevTools on the generator page)",
        url="https://perchance.org/ai-text-to-image-generator",
    )

    def is_available(self) -> bool:
        cfg = load_image_gen_config("perchance")
        key = _auto_ensure_key(cfg)
        return bool(key)

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "perchance-ai-text-to-image",
                "display": "Perchance AI (free)",
                "strengths": "Fast, unlimited, no login. Good for casual use.",
                "price": "free (rate limited)",
            }
        ]

    def default_model(self) -> Optional[str]:
        return "perchance-ai-text-to-image"

    def capabilities(self) -> Dict[str, Any]:
        return {"modalities": ["text"], "max_reference_images": 0}

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        *,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)

        fail = lambda msg, code, **extra: error_response(
            "perchance", msg, code, prompt=prompt, aspect_ratio=aspect, **extra
        )

        if image_url or reference_image_urls:
            return fail(
                "Perchance provider only supports text-to-image (no image editing / reference images).",
                "modality_unsupported",
            )

        if not prompt:
            return prompt_required_error("perchance", aspect)

        cfg = load_image_gen_config("perchance")
        user_key = _auto_ensure_key(cfg)

        if not user_key:
            return fail(
                "No Perchance userKey configured. "
                "Run `hermes perchance key fetch` (best effort) or `hermes perchance key set <key>`. "
                "Manual method: visit https://perchance.org/ai-text-to-image-generator, open DevTools → Network, generate, copy the userKey.",
                "auth_required",
            )

        resolution = _resolve_resolution(aspect)
        guidance = kwargs.get("guidance_scale", 7)
        negative = kwargs.get("negative_prompt", "nudity, text, watermark, low quality")

        prompt_query = quote("'" + prompt)
        neg_query = quote("'" + negative)

        request_id = str(random.random())
        cache_bust = str(random.random())

        params = {
            "prompt": prompt_query,
            "negativePrompt": neg_query,
            "userKey": user_key,
            "__cache_bust": cache_bust,
            "seed": "-1",
            "resolution": resolution,
            "guidanceScale": str(guidance),
            "channel": "ai-text-to-image-generator",
            "subChannel": "public",
            "requestId": request_id,
        }

        try:
            create_resp = requests.get(
                PERCHANCE_CREATE_URL,
                params=params,
                timeout=30,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://perchance.org/ai-text-to-image-generator",
                },
            )

            if create_resp.status_code == 403 or "Just a moment" in create_resp.text:
                return fail(
                    "Perchance is blocking the request (Cloudflare). "
                    "Try using a real browser session to obtain a fresh userKey, or wait a bit.",
                    "rate_limited_or_blocked",
                )

            if "invalid_key" in create_resp.text.lower():
                try:
                    if CACHE_KEY_FILE.exists():
                        CACHE_KEY_FILE.unlink()
                except Exception:
                    pass
                new_key = _try_fetch_key_automatically()
                if new_key:
                    return fail(
                        "Perchance key was invalid but a fresh one was auto-fetched. Please retry your request.",
                        "auth_required",
                    )
                return fail(
                    "Perchance userKey is invalid or expired. Run `hermes perchance key fetch` or obtain a fresh one manually.",
                    "auth_required",
                )

            data = create_resp.json()
            image_id = data.get("imageId")
            if not image_id:
                return fail(
                    f"Unexpected response from Perchance (no imageId): {create_resp.text[:200]}",
                    "api_error",
                )

            dl_resp = requests.get(
                PERCHANCE_DOWNLOAD_URL,
                params={"imageId": image_id},
                timeout=60,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://perchance.org/ai-text-to-image-generator",
                },
            )
            dl_resp.raise_for_status()

            if len(dl_resp.content) < 1000:
                return fail("Perchance returned a very small/empty image file.", "empty_response")

            images_dir = Path.home() / ".hermes" / "cache" / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            filename = f"perchance_{int(time.time())}_{image_id[:8]}.jpg"
            image_path = images_dir / filename
            image_path.write_bytes(dl_resp.content)

            _save_cached_key(user_key)

            return success_response(
                image=str(image_path),
                model="perchance-ai-text-to-image",
                prompt=prompt,
                aspect_ratio=aspect,
                provider="perchance",
                extra={
                    "resolution": resolution,
                    "image_id": image_id,
                    "guidance_scale": guidance,
                },
            )

        except requests.exceptions.RequestException as exc:
            logger.debug("Perchance request failed", exc_info=True)
            return fail(f"Network error contacting Perchance: {exc}", "api_error")
        except Exception as exc:
            logger.debug("Perchance generation failed", exc_info=True)
            return fail(f"Perchance generation error: {exc}", "api_error")


def register(ctx) -> None:
    """Plugin entry point — register provider and CLI helper."""
    ctx.register_image_gen_provider(PerchanceImageGenProvider())

    # Register CLI subcommand "perchance"
    try:
        from . import cli as _cli
        ctx.register_cli_command(
            "perchance",
            setup_fn=_cli.register_cli,
            handler_fn=_cli._perchance_main,
        )
    except Exception as exc:
        logger.debug("Could not register Perchance CLI: %s", exc)


__all__ = ["PerchanceImageGenProvider", "register"]