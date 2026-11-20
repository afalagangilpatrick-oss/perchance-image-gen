#!/usr/bin/env python3
"""
Standalone helper to fetch a Perchance userKey.

Run this directly (outside Hermes) when you need a fresh key:

    python fetch_perchance_key.py
    python fetch_perchance_key.py --visible          # show browser window
    python fetch_perchance_key.py --browser firefox

Requirements (optional but strongly recommended):
    pip install playwright
    playwright install chromium   # or firefox

The script will try Playwright first. If not installed or it fails, it prints
clear manual DevTools instructions.

After getting a key, you can:
    export PERCHANCE_USER_KEY="the64charhexkey"
    # or
    hermes perchance key set the64charhexkey
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

CACHE_FILE = Path.home() / ".hermes" / "cache" / "perchance_user_key.txt"


def _save_key(key: str):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(key.strip())
    print(f"Saved to cache: {CACHE_FILE}")


def _verify_key(candidate: str) -> bool:
    if not requests:
        return False
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


def fetch_with_playwright(headless: bool = True, browser: str = "chromium") -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed. Install with:")
        print("  pip install playwright")
        print("  playwright install chromium")
        return None

    key = None

    def extract_from_url(url: str):
        if "userKey=" not in url:
            return None
        try:
            qs = url.split("?", 1)[1]
            for p in qs.split("&"):
                if p.startswith("userKey="):
                    cand = p.split("=", 1)[1].split("&")[0]
                    if len(cand) == 64:
                        return cand
        except Exception:
            return None

    try:
        with sync_playwright() as p:
            launch = getattr(p, browser, p.chromium)
            b = launch.launch(headless=headless)
            ctx = b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            page = ctx.new_page()

            def on_req(req):
                nonlocal key
                if "generate" in req.url and "perchance" in req.url:
                    k = extract_from_url(req.url)
                    if k:
                        key = k

            page.on("request", on_req)
            page.goto("https://perchance.org/ai-text-to-image-generator", wait_until="domcontentloaded", timeout=30000)

            # Try to trigger generation
            for sel in ["button:has-text('Generate')", "#generateButtonEl", "button.generate-button"]:
                try:
                    page.click(sel, timeout=4000)
                    break
                except Exception:
                    continue

            # Wait for key
            for _ in range(30):
                if key:
                    break
                page.wait_for_timeout(700)

            b.close()

    except Exception as e:
        print(f"Playwright error: {e}")
        return None

    if key and _verify_key(key):
        return key
    return key


def manual_instructions():
    print("\n" + "=" * 60)
    print("MANUAL KEY EXTRACTION (most reliable method)")
    print("=" * 60)
    print("1. Open https://perchance.org/ai-text-to-image-generator in a normal browser")
    print("2. Press F12 → go to the Network tab")
    print("3. Type any prompt and click the Generate button")
    print("4. In the network list, click the request that goes to:")
    print("     https://image-generation.perchance.org/api/generate")
    print("5. Look in the URL or Params for 'userKey=xxxxxxxxxxxxxxxx...'")
    print("   (exactly 64 hexadecimal characters)")
    print("6. Copy that value")
    print()
    print("Then run one of:")
    print("  hermes perchance key set THE_KEY_HERE")
    print("  export PERCHANCE_USER_KEY=THE_KEY_HERE")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fetch Perchance userKey helper")
    parser.add_argument("--visible", action="store_true", help="Show browser window (helps bypass Cloudflare)")
    parser.add_argument("--browser", default="chromium", choices=["chromium", "firefox"])
    args = parser.parse_args()

    print("Fetching Perchance userKey...")

    key = fetch_with_playwright(headless=not args.visible, browser=args.browser)

    if key:
        print(f"\n✅ Got key: {key[:8]}...{key[-8:]}")
        _save_key(key)
        print("\nYou can now use it with Hermes or set the env var.")
        return 0

    print("\n❌ Automatic fetch did not succeed.")
    manual_instructions()
    return 1


if __name__ == "__main__":
    sys.exit(main())