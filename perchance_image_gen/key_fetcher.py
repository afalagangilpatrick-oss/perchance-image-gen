"""
Playwright-based key fetcher for Perchance (standalone).

This module is optional — only needed if you want automatic key fetching.
Install with: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import logging
import random
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def fetch_key_with_playwright(
    headless: bool = True,
    browser: str = "chromium",
    timeout: int = 60,
) -> Optional[str]:
    """
    Attempt to obtain a fresh Perchance userKey using Playwright.

    Returns the 64-char hex key or None.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout, Error as PlaywrightError
    except ImportError:
        logger.info("Playwright not installed. Skipping auto key fetch.")
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

    def _verify_key(candidate: str) -> bool:
        try:
            r = requests.get(
                "https://image-generation.perchance.org/api/checkVerificationStatus",
                params={"userKey": candidate, "__cacheBust": str(random.random())},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            return "not_verified" not in r.text.lower() and r.status_code == 200
        except Exception:
            return False

    browsers_to_try = [browser, "firefox", "chromium"] if browser != "chromium" else ["chromium", "firefox"]

    for btype in browsers_to_try:
        try:
            with sync_playwright() as p:
                launch_browser = getattr(p, btype, p.chromium)
                browser_instance = launch_browser.launch(
                    headless=headless,
                    args=["--disable-blink-features=AutomationControlled"] if not headless else None,
                )
                context = browser_instance.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1366, "height": 768},
                    locale="en-US",
                )
                page = context.new_page()

                def on_request(request):
                    nonlocal key
                    if "generate" in request.url and "perchance" in request.url:
                        k = _extract_key_from_url(request.url)
                        if k:
                            key = k

                page.on("request", on_request)

                page.goto("https://perchance.org/ai-text-to-image-generator", wait_until="domcontentloaded", timeout=30000)

                try:
                    page.wait_for_selector("iframe, button, input, #generateButtonEl", timeout=8000)
                except Exception:
                    pass

                # Handle iframe
                try:
                    iframe = page.query_selector("iframe")
                    if iframe:
                        frame = iframe.content_frame()
                        if frame:
                            page = frame
                except Exception:
                    pass

                # Click generate
                clicked = False
                selectors = [
                    "button:has-text('Generate')",
                    "button#generateButtonEl",
                    "button.generate-button",
                    "input[type=submit]",
                    "#generate",
                    "text=Generate",
                ]
                for sel in selectors:
                    try:
                        page.click(sel, timeout=3000)
                        clicked = True
                        break
                    except Exception:
                        continue

                if not clicked:
                    try:
                        for sel in ["textarea", "input[type='text']", "#prompt"]:
                            page.fill(sel, "test key fetch", timeout=2000)
                            page.keyboard.press("Enter")
                            clicked = True
                            break
                    except Exception:
                        pass

                # Wait for key
                start = time.time()
                while key is None and (time.time() - start) < min(timeout, 25):
                    page.wait_for_timeout(700)
                    try:
                        page.wait_for_request(lambda r: "generate" in r.url and "perchance" in r.url, timeout=2000)
                    except Exception:
                        pass

                browser_instance.close()

                if key and _verify_key(key):
                    return key
                if key:
                    return key  # return even if verification failed

        except PlaywrightTimeout:
            continue
        except PlaywrightError as exc:
            logger.debug("Playwright %s error: %s", btype, exc)
            continue
        except Exception as exc:
            logger.debug("Key fetch (%s) failed: %s", btype, exc)
            continue

    return None
