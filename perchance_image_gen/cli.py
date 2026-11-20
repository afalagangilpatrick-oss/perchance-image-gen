"""Standalone CLI for perchance_image_gen."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import PerchanceGenerator


def main_generate(args: argparse.Namespace) -> int:
    gen = PerchanceGenerator()
    result = gen.generate(
        prompt=args.prompt,
        aspect_ratio=args.aspect,
        guidance_scale=args.guidance,
        negative_prompt=args.negative,
        seed=args.seed,
        resolution=args.resolution,
    )

    if not result.get("success"):
        print("Error:", result.get("error"))
        return 1

    path = result.get("image")
    print(f"✅ Saved: {path}")

    if args.open:
        import subprocess
        import os
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", path], check=False)
        elif sys.platform == "win32":
            os.startfile(path)

    return 0


def main_fetch_key(args: argparse.Namespace = None) -> int:
    if args is None:
        # Called directly from entry point without argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--visible", action="store_true")
        parser.add_argument("--browser", default="chromium", choices=["chromium", "firefox"])
        args = parser.parse_args([])  # defaults

    gen = PerchanceGenerator()
    key = gen.fetch_key(headless=not getattr(args, "visible", False), browser=getattr(args, "browser", "chromium"))
    if key:
        print(f"✅ Fetched key: {key[:8]}...{key[-8:]}")
        print("Saved to cache.")
        return 0
    print("❌ Could not fetch key automatically.")
    print("Use manual DevTools method or run with --visible.")
    return 1


def main_status(args: argparse.Namespace) -> int:
    gen = PerchanceGenerator()
    key = gen._get_user_key()
    if key:
        print(f"Key present: {key[:8]}...{key[-8:]}")
        valid = gen._validate_key(key)
        print(f"Validates: {'yes' if valid else 'no (may need refresh)'}")
    else:
        print("No key configured.")
        print("Run: perchance-key-fetch or set PERCHANCE_USER_KEY")
    return 0


def cli():
    parser = argparse.ArgumentParser(prog="perchance", description="Perchance free image generator (standalone)")
    sub = parser.add_subparsers(dest="cmd")

    # generate
    p_gen = sub.add_parser("generate", help="Generate an image")
    p_gen.add_argument("prompt")
    p_gen.add_argument("--aspect", "-a", default="landscape", choices=["landscape", "square", "portrait"])
    p_gen.add_argument("--resolution", "-r")
    p_gen.add_argument("--guidance", "-g", type=float, default=7.0)
    p_gen.add_argument("--negative", "-n", default="nudity, text, watermark, low quality")
    p_gen.add_argument("--seed", default="-1")
    p_gen.add_argument("--open", action="store_true")
    p_gen.set_defaults(func=main_generate)

    # key fetch
    p_key = sub.add_parser("key-fetch", help="Fetch a new userKey")
    p_key.add_argument("--visible", action="store_true")
    p_key.add_argument("--browser", default="chromium", choices=["chromium", "firefox"])
    p_key.set_defaults(func=main_fetch_key)

    # status
    p_status = sub.add_parser("status", help="Show key status")
    p_status.set_defaults(func=main_status)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(cli())
