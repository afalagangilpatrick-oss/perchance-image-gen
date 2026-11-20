"""CLI helper for the Perchance image generation plugin.

Usage examples:
  hermes perchance status
  hermes perchance key get
  hermes perchance key set <64-hex-key>
  hermes perchance key clear
  hermes perchance generate "a cute robot in a neon city" --aspect landscape
  hermes perchance open
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from agent.image_gen_provider import DEFAULT_ASPECT_RATIO

# Local imports (will be relative when loaded as plugin)
try:
    from . import (
        PerchanceImageGenProvider,
        _get_cached_key,
        _save_cached_key,
        CACHE_KEY_FILE,
        _try_fetch_key_automatically,
        _validate_key,
    )
    from .__init__ import load_image_gen_config
except ImportError:
    # Fallback when developing directly
    from plugins.image_gen.perchance import PerchanceImageGenProvider  # type: ignore
    from plugins.image_gen.perchance.__init__ import (  # type: ignore
        _get_cached_key,
        _save_cached_key,
        CACHE_KEY_FILE,
        _try_fetch_key_automatically,
        _validate_key,
        load_image_gen_config,
    )


def _mask_key(key: Optional[str]) -> str:
    if not key:
        return "(none)"
    if len(key) <= 8:
        return key
    return key[:4] + "..." + key[-4:]


def register_cli(subparser: argparse.ArgumentParser) -> None:
    """Register the 'perchance' subcommand and its actions."""
    subparser.description = "Perchance free image generator controls and helpers"

    subs = subparser.add_subparsers(dest="perchance_action")

    # status
    p_status = subs.add_parser("status", help="Show Perchance provider status and key info")
    p_status.set_defaults(func=_cmd_status)

    # key management
    p_key = subs.add_parser("key", help="Manage the Perchance userKey")
    key_subs = p_key.add_subparsers(dest="key_action")

    p_key_get = key_subs.add_parser("get", help="Show current key (masked)")
    p_key_get.set_defaults(func=_cmd_key_get)

    p_key_set = key_subs.add_parser("set", help="Set and cache a userKey")
    p_key_set.add_argument("key", help="64-character hex userKey")
    p_key_set.set_defaults(func=_cmd_key_set)

    p_key_clear = key_subs.add_parser("clear", help="Remove cached key")
    p_key_clear.set_defaults(func=_cmd_key_clear)

    p_key_validate = key_subs.add_parser("validate", help="Validate the current key")
    p_key_validate.set_defaults(func=_cmd_key_validate)

    # generate (direct CLI generation, bypasses chat)
    p_gen = subs.add_parser("generate", help="Generate an image directly from the terminal")
    p_gen.add_argument("prompt", help="Text prompt for the image")
    p_gen.add_argument(
        "--aspect", "-a",
        choices=["landscape", "square", "portrait"],
        default=DEFAULT_ASPECT_RATIO,
        help="Aspect ratio (default: landscape)"
    )
    p_gen.add_argument(
        "--resolution", "-r",
        default=None,
        help="Direct resolution override (e.g. 512x768, 768x512). Overrides --aspect."
    )
    p_gen.add_argument(
        "--guidance", "-g",
        type=float,
        default=7.0,
        help="Guidance scale (default: 7, range ~1-30)"
    )
    p_gen.add_argument(
        "--negative", "-n",
        default="nudity, text, watermark, low quality",
        help="Negative prompt"
    )
    p_gen.add_argument(
        "--out", "-o",
        default=None,
        help="Optional output path for the image (default: cache)"
    )
    p_gen.add_argument(
        "--seed",
        default="-1",
        help="Seed for reproducibility (-1 for random)"
    )
    p_gen.add_argument(
        "--count", "-c", "--num",
        type=int,
        default=1,
        help="Number of images to generate (default 1)"
    )
    p_gen.add_argument(
        "--open",
        action="store_true",
        help="Open the generated image(s) after creation"
    )
    p_gen.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output"
    )
    p_gen.add_argument(
        "--save-dir",
        default=None,
        help="Directory to save images (default: ~/.hermes/cache/images)"
    )
    p_gen.set_defaults(func=_cmd_generate)

    # open the web UI
    p_open = subs.add_parser("open", aliases=["web"], help="Open the Perchance generator page in your browser")
    p_open.set_defaults(func=_cmd_open)

    # list models
    p_models = subs.add_parser("models", help="List available models from this provider")
    p_models.set_defaults(func=_cmd_models)

    # quick test
    p_test = subs.add_parser("test", help="Run a quick test generation")
    p_test.add_argument("--prompt", default="a cute cat wearing sunglasses, photorealistic", help="Test prompt")
    p_test.set_defaults(func=_cmd_test)

    # show config
    p_config = subs.add_parser("config", help="Show relevant Perchance configuration")
    p_config.set_defaults(func=_cmd_config)

    # list recent images
    p_recent = subs.add_parser("recent", aliases=["images", "list"], help="List recently generated images from cache")
    p_recent.add_argument("--limit", "-n", type=int, default=10, help="How many to show")
    p_recent.set_defaults(func=_cmd_recent)

    # clear caches
    p_clear = subs.add_parser("clear-cache", help="Clear cached keys and/or generated images")
    p_clear.add_argument("--keys", action="store_true", help="Only clear keys")
    p_clear.add_argument("--images", action="store_true", help="Only clear images")
    p_clear.set_defaults(func=_cmd_clear_cache)

    # fetch with options
    p_key_fetch = key_subs.add_parser("fetch", aliases=["auto", "refresh"], help="Attempt automatic key fetch (Playwright)")
    p_key_fetch.add_argument("--visible", action="store_true", help="Run browser visibly (helps with Cloudflare)")
    p_key_fetch.add_argument("--browser", default="chromium", choices=["chromium", "firefox"], help="Browser engine")
    p_key_fetch.set_defaults(func=_cmd_key_fetch)

    subparser.set_defaults(func=_perchance_main)


def _perchance_main(args: argparse.Namespace) -> int:
    action = getattr(args, "perchance_action", None)
    if not action:
        print("Usage: hermes perchance {status|key|generate|open|models|test|config|recent|clear-cache}")
        return 2

    # The subparsers set func directly
    if hasattr(args, "func"):
        return args.func(args) or 0
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    prov = PerchanceImageGenProvider()
    cached = _get_cached_key()
    env_key = os.environ.get("PERCHANCE_USER_KEY", "").strip()
    cfg = prov.load_image_gen_config("perchance") if hasattr(prov, "load_image_gen_config") else {}  # type: ignore
    cfg_key = cfg.get("user_key") or cfg.get("userKey")

    print("Perchance Provider Status")
    print("=========================")
    print(f"Available:          {prov.is_available()}")
    print(f"Provider ID/Name:   {prov.name}")
    print(f"Label:              {prov.label}")
    print(f"Models:             {[m['display'] for m in prov.list_models()]}")
    print(f"Capabilities:       {prov.capabilities()}")
    print()
    print("Key sources (priority: env > config > cache):")
    print(f"  ENV  PERCHANCE_USER_KEY: {'set (' + _mask_key(env_key) + ')' if env_key else 'not set'}")
    print(f"  Config (image_gen.perchance): {'set' if cfg_key else 'not set'}")
    print(f"  Cached file:        {_mask_key(cached)}")
    print()
    if prov.is_available():
        print("Ready to generate images in chat or via 'hermes perchance generate'")
    else:
        print("Not available yet — set a userKey with 'hermes perchance key set <key>'")
    return 0


def _cmd_key_get(args: argparse.Namespace) -> int:
    key = _get_cached_key()
    env = os.environ.get("PERCHANCE_USER_KEY", "")
    print("Current effective key (masked):")
    if env:
        print(f"  From ENV: {_mask_key(env)}")
    if key:
        print(f"  From cache: {_mask_key(key)}")
    if not env and not key:
        print("  (no key configured)")
    return 0


def _cmd_key_set(args: argparse.Namespace) -> int:
    key = args.key.strip()
    if len(key) != 64 or not all(c in "0123456789abcdefABCDEF" for c in key):
        print("Error: key must be exactly 64 hexadecimal characters.")
        return 1
    _save_cached_key(key)
    # Also set in env for current session if possible (best effort)
    os.environ["PERCHANCE_USER_KEY"] = key
    print(f"Key saved and cached: {_mask_key(key)}")
    print("It will be used for future generations.")
    return 0


def _cmd_key_clear(args: argparse.Namespace) -> int:
    try:
        if CACHE_KEY_FILE.exists():
            CACHE_KEY_FILE.unlink()
        print("Cached key cleared.")
    except Exception as e:
        print(f"Could not clear cache: {e}")
        return 1
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    prov = PerchanceImageGenProvider()
    if not prov.is_available():
        print("Perchance is not available (no valid userKey).")
        print("Run: hermes perchance key fetch  or  hermes perchance key set <your-key>")
        return 1

    if not args.quiet:
        print(f"Generating with Perchance: {args.prompt[:80]}...")

    results = []
    for i in range(max(1, args.count)):
        if args.count > 1 and not args.quiet:
            print(f"  [{i+1}/{args.count}] ...")

        result = prov.generate(
            prompt=args.prompt,
            aspect_ratio=args.aspect,
            guidance_scale=args.guidance,
            negative_prompt=args.negative,
            seed=args.seed,
        )

        if not result.get("success"):
            print("Generation failed:")
            print(result.get("error", "Unknown error"))
            return 1

        image_path = result.get("image")
        results.append(image_path)
        if not args.quiet:
            print(f"  Saved: {image_path}")

        if args.out:
            try:
                import shutil
                out_path = args.out
                if args.count > 1:
                    stem, ext = os.path.splitext(args.out)
                    out_path = f"{stem}_{i+1}{ext}"
                shutil.copy(image_path, out_path)
                if not args.quiet:
                    print(f"  Copied to: {out_path}")
            except Exception as e:
                print(f"Could not copy: {e}")

        if args.open:
            try:
                if sys.platform == "darwin":
                    subprocess.run(["open", image_path], check=False)
                elif sys.platform.startswith("linux"):
                    subprocess.run(["xdg-open", image_path], check=False)
            except Exception:
                pass

    if not args.quiet:
        print(f"Done. {len(results)} image(s) generated.")
    return 0


def _cmd_open(args: argparse.Namespace) -> int:
    url = "https://perchance.org/ai-text-to-image-generator"
    print(f"Opening {url} ...")
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", url], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", url], check=False)
        elif sys.platform == "win32":
            os.startfile(url)  # type: ignore
        else:
            print(f"Please open manually: {url}")
    except Exception as e:
        print(f"Could not open browser automatically: {e}")
        print(f"URL: {url}")
    return 0


def _cmd_models(args: argparse.Namespace) -> int:
    prov = PerchanceImageGenProvider()
    print("Perchance Models:")
    for m in prov.list_models():
        print(f"  - {m.get('display', m.get('id'))}")
        print(f"    ID: {m.get('id')}")
        print(f"    Strengths: {m.get('strengths', 'N/A')}")
        print(f"    Price: {m.get('price', 'N/A')}")
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    print("Running quick test generation...")
    return _cmd_generate(argparse.Namespace(
        prompt=args.prompt,
        aspect="square",
        resolution=None,
        guidance=7.0,
        negative="nudity, text, watermark",
        out=None,
        seed="-1",
        count=1,
        open=False,
        quiet=False,
        save_dir=None,
    ))


def _cmd_config(args: argparse.Namespace) -> int:
    prov = PerchanceImageGenProvider()
    cfg = load_image_gen_config("perchance") if 'load_image_gen_config' in globals() else {}
    env = os.environ.get("PERCHANCE_USER_KEY", "")
    cached = _get_cached_key()

    print("Perchance Configuration:")
    print(f"  Provider available: {prov.is_available()}")
    print(f"  ENV PERCHANCE_USER_KEY: {'set' if env else 'not set'}")
    print(f"  Config key present: {bool(cfg.get('user_key') or cfg.get('userKey'))}")
    print(f"  Cached key: {_mask_key(cached)}")
    print(f"  Cache file: {CACHE_KEY_FILE}")
    print()
    print("To set key: hermes perchance key set <key>   or   hermes perchance key fetch")
    return 0


def _cmd_key_fetch(args: argparse.Namespace) -> int:
    print("Attempting to automatically fetch a fresh Perchance userKey...")
    print("Playwright recommended: pip install playwright && playwright install")
    if getattr(args, "visible", False):
        print("Running in VISIBLE mode (browser window will appear).")
    print()

    headless = not getattr(args, "visible", False)
    browser = getattr(args, "browser", "chromium")

    key = _try_fetch_key_automatically(headless=headless)
    if key:
        _save_cached_key(key)
        os.environ["PERCHANCE_USER_KEY"] = key
        print(f"✅ Successfully fetched and cached key: {_mask_key(key)}")
        print("You can now use Perchance for image generation.")
        return 0

    print("❌ Automatic fetch failed.")
    print()
    print("Manual instructions (most reliable):")
    print("  1. Open https://perchance.org/ai-text-to-image-generator in Chrome/Firefox")
    print("  2. Open DevTools (F12) → Network tab")
    print("  3. Type a prompt and click Generate")
    print("  4. Find request to image-generation.perchance.org/api/generate")
    print("  5. Copy the userKey=... value (exactly 64 hex chars)")
    print("  6. Run: hermes perchance key set <key>")
    print()
    print("Tip: Try 'hermes perchance key fetch --visible' if headless is blocked by Cloudflare.")
    return 1


def _cmd_key_validate(args: argparse.Namespace) -> int:
    key = _get_cached_key()
    env_key = os.environ.get("PERCHANCE_USER_KEY", "").strip()
    effective = env_key or key

    if not effective:
        print("No key configured.")
        return 1

    print(f"Validating key: {_mask_key(effective)} ...")
    if _validate_key(effective):
        print("✅ Key appears valid (format + basic check passed).")
        return 0
    else:
        print("❌ Key validation failed (may be expired or blocked).")
        print("Try: hermes perchance key fetch   or get a fresh one manually.")
        return 1


def _cmd_recent(args: argparse.Namespace) -> int:
    images_dir = Path.home() / ".hermes" / "cache" / "images"
    if not images_dir.exists():
        print("No images cache directory found.")
        return 0

    files = sorted(
        images_dir.glob("perchance_*.jpg"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )[:args.limit]

    if not files:
        print("No recent Perchance images found.")
        return 0

    print(f"Recent Perchance images (last {len(files)}):")
    for f in files:
        size = f.stat().st_size
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))
        print(f"  {f.name}  ({size/1024:.1f} KB)  {mtime}")
    return 0


def _cmd_clear_cache(args: argparse.Namespace) -> int:
    cleared = []
    do_keys = args.keys or not (args.keys or args.images)
    do_images = args.images or not (args.keys or args.images)

    if do_keys:
        try:
            if CACHE_KEY_FILE.exists():
                CACHE_KEY_FILE.unlink()
                cleared.append("key cache")
        except Exception as e:
            print(f"Could not clear key cache: {e}")

    if do_images:
        images_dir = Path.home() / ".hermes" / "cache" / "images"
        try:
            if images_dir.exists():
                count = 0
                for f in images_dir.glob("perchance_*.jpg"):
                    f.unlink()
                    count += 1
                cleared.append(f"{count} image(s)")
        except Exception as e:
            print(f"Could not clear images: {e}")

    if cleared:
        print("Cleared: " + ", ".join(cleared))
    else:
        print("Nothing to clear.")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    prov = PerchanceImageGenProvider()
    if not prov.is_available():
        print("Perchance is not available (no valid userKey).")
        print("Run: hermes perchance key fetch  or  hermes perchance key set <your-key>")
        return 1

    if not args.quiet:
        print(f"Generating with Perchance: {args.prompt[:80]}...")

    # Determine resolution
    if args.resolution:
        resolution = args.resolution
    else:
        aspect = args.aspect
        # Reuse internal resolver if available, else fallback
        try:
            from . import _resolve_resolution
            resolution = _resolve_resolution(aspect)
        except Exception:
            res_map = {"landscape": "1536x1024", "square": "1024x1024", "portrait": "1024x1536"}
            resolution = res_map.get(aspect, "1024x1024")

    results = []
    for i in range(max(1, args.count)):
        if args.count > 1 and not args.quiet:
            print(f"  [{i+1}/{args.count}] ...")

        result = prov.generate(
            prompt=args.prompt,
            aspect_ratio=args.aspect,
            guidance_scale=args.guidance,
            negative_prompt=args.negative,
            seed=args.seed,
            resolution=resolution,  # pass extra if supported
        )

        if not result.get("success"):
            print("Generation failed:")
            print(result.get("error", "Unknown error"))
            return 1

        image_path = result.get("image")
        results.append(image_path)
        if not args.quiet:
            print(f"  Saved: {image_path}")

        # Handle save-dir
        if args.save_dir or args.out:
            try:
                import shutil
                target_dir = Path(args.save_dir).expanduser() if args.save_dir else Path.home() / ".hermes" / "cache" / "images"
                target_dir.mkdir(parents=True, exist_ok=True)
                out_path = args.out
                if not out_path:
                    out_path = target_dir / Path(image_path).name
                else:
                    out_path = Path(out_path)
                    if args.count > 1:
                        stem, ext = out_path.stem, out_path.suffix
                        out_path = out_path.with_name(f"{stem}_{i+1}{ext}")
                shutil.copy(image_path, out_path)
                if not args.quiet:
                    print(f"  Copied to: {out_path}")
            except Exception as e:
                print(f"Could not copy: {e}")

        if args.open:
            try:
                if sys.platform == "darwin":
                    subprocess.run(["open", image_path], check=False)
                elif sys.platform.startswith("linux"):
                    subprocess.run(["xdg-open", image_path], check=False)
            except Exception:
                pass

    if not args.quiet:
        print(f"Done. {len(results)} image(s) generated.")
    return 0


# For direct testing
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    register_cli(parser)
    args = parser.parse_args()
    sys.exit(_perchance_main(args) or 0)