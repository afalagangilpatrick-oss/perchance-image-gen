#!/usr/bin/env python3
"""
Automation script to keep the Perchance plugin repo up to date.

This script syncs between:
  - Active Hermes installation: ~/.hermes/plugins/image_gen/perchance/
  - Source repo: the directory containing this script (parent of scripts/)

Typical workflow:
  1. Edit the plugin inside Hermes (in the active location).
  2. Run this script to push changes back to the source repo.
  3. Then git commit/push from the repo.

Usage:
    python scripts/sync.py --to-repo          # Active → Repo (most common for dev)
    python scripts/sync.py --to-active        # Repo → Active (deploy changes)
    python scripts/sync.py --both             # Bidirectional (careful)
    python scripts/sync.py --status           # Show what would change

Options:
    --dry-run     Show actions without doing them
    --git         After sync, run git status / add changes (when going to-repo)
    --force       Overwrite without confirmation
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

# === CONFIGURATION ===
REPO_ROOT = Path(__file__).parent.parent.resolve()
ACTIVE_PLUGIN = Path.home() / ".hermes" / "plugins" / "image_gen" / "perchance"

# What to sync (relative to the plugin dir)
PLUGIN_RELATIVE_FILES = [
    # Core Hermes plugin files
    "__init__.py",
    "cli.py",
    "plugin.yaml",
    "README.md",
    # Standalone helper (copied into active for convenience)
    "fetch_perchance_key.py",
    # Guides
    "PERCHANCE_HERMES_PLUGIN_GUIDE.md",
]

# Also sync the new portable package from repo root
PORTABLE_PACKAGE = "perchance_image_gen"

# Files/dirs to never copy
EXCLUDES = {
    "__pycache__",
    "*.pyc",
    ".git",
    "egg-info",
    "build",
    "dist",
    "*.log",
    "generated_images",
    "last_key.txt",
}


def should_exclude(path: Path) -> bool:
    name = path.name
    for pat in EXCLUDES:
        if pat.startswith("*.") and name.endswith(pat[1:]):
            return True
        if name == pat:
            return True
    return False


def copy_file(src: Path, dst: Path, dry_run: bool = False) -> bool:
    if should_exclude(src):
        return False
    if not src.exists():
        return False

    if dry_run:
        print(f"[DRY] Would copy: {src} → {dst}")
        return True

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    try:
        rel = src.relative_to(REPO_ROOT)
    except ValueError:
        rel = src.name
    print(f"Copied: {rel} → {dst}")
    return True


def sync_hermes_plugin_to_repo(dry_run: bool = False) -> List[str]:
    """Copy changes from active Hermes plugin back to the source repo."""
    changes = []
    if not ACTIVE_PLUGIN.exists():
        print(f"Active plugin dir not found: {ACTIVE_PLUGIN}")
        return changes

    plugin_dir_in_repo = REPO_ROOT / "plugins" / "image_gen" / "perchance"
    plugin_dir_in_repo.mkdir(parents=True, exist_ok=True)

    for rel in PLUGIN_RELATIVE_FILES:
        src = ACTIVE_PLUGIN / rel
        dst = plugin_dir_in_repo / rel
        if src.exists() and (not dst.exists() or not filecmp.cmp(src, dst, shallow=False)):
            if copy_file(src, dst, dry_run):
                changes.append(str(rel))

    # Also copy the helper if it's at top level of active
    for extra in ["fetch_perchance_key.py", "PERCHANCE_HERMES_PLUGIN_GUIDE.md"]:
        src = ACTIVE_PLUGIN / extra
        dst = REPO_ROOT / extra
        if src.exists() and (not dst.exists() or not filecmp.cmp(src, dst, shallow=False)):
            if copy_file(src, dst, dry_run):
                changes.append(extra)

    return changes


def sync_repo_to_hermes(dry_run: bool = False) -> List[str]:
    """Deploy changes from source repo to the active Hermes location."""
    changes = []
    plugin_dir_in_repo = REPO_ROOT / "plugins" / "image_gen" / "perchance"

    if not plugin_dir_in_repo.exists():
        print("No plugin dir in repo to sync from.")
        return changes

    ACTIVE_PLUGIN.mkdir(parents=True, exist_ok=True)

    # Sync the Hermes plugin files
    for rel in PLUGIN_RELATIVE_FILES:
        src = plugin_dir_in_repo / rel
        dst = ACTIVE_PLUGIN / rel
        if src.exists() and (not dst.exists() or not filecmp.cmp(src, dst, shallow=False)):
            if copy_file(src, dst, dry_run):
                changes.append(f"hermes/{rel}")

    # Sync the standalone package
    src_pkg = REPO_ROOT / PORTABLE_PACKAGE
    dst_pkg = ACTIVE_PLUGIN / PORTABLE_PACKAGE   # put it inside for easy access
    if src_pkg.exists():
        for root, dirs, files in os.walk(src_pkg):
            rootp = Path(root)
            rel = rootp.relative_to(src_pkg)
            for f in files:
                if should_exclude(Path(f)):
                    continue
                src_f = rootp / f
                dst_f = dst_pkg / rel / f
                if not dst_f.exists() or not filecmp.cmp(src_f, dst_f, shallow=False):
                    if copy_file(src_f, dst_f, dry_run):
                        changes.append(f"portable/{rel}/{f}")

    # Also copy top-level helper and guide
    for extra in ["fetch_perchance_key.py", "PERCHANCE_HERMES_PLUGIN_GUIDE.md"]:
        src = REPO_ROOT / extra
        dst = ACTIVE_PLUGIN / extra
        if src.exists() and (not dst.exists() or not filecmp.cmp(src, dst, shallow=False)):
            if copy_file(src, dst, dry_run):
                changes.append(extra)

    return changes


def sync_both(dry_run: bool = False) -> None:
    print("=== Syncing Hermes active → Repo ===")
    c1 = sync_hermes_plugin_to_repo(dry_run)
    print("=== Syncing Repo → Hermes active ===")
    c2 = sync_repo_to_hermes(dry_run)
    print(f"\nTotal changes: {len(c1) + len(c2)}")


def show_status() -> None:
    print("=== Status: Active vs Repo ===")
    print(f"Repo root:     {REPO_ROOT}")
    print(f"Active plugin: {ACTIVE_PLUGIN}")
    print()

    if not ACTIVE_PLUGIN.exists():
        print("Active plugin directory does not exist yet.")
        return

    plugin_repo = REPO_ROOT / "plugins" / "image_gen" / "perchance"

    print("Hermes plugin files:")
    for rel in PLUGIN_RELATIVE_FILES:
        src = ACTIVE_PLUGIN / rel
        dst = plugin_repo / rel
        if not src.exists():
            print(f"  MISSING in active: {rel}")
        elif not dst.exists():
            print(f"  NEW in active (not in repo): {rel}")
        elif not filecmp.cmp(src, dst, shallow=False):
            print(f"  DIFFERS: {rel}")
        else:
            print(f"  OK: {rel}")

    print("\nPortable package in repo:")
    pkg = REPO_ROOT / PORTABLE_PACKAGE
    if pkg.exists():
        print(f"  {PORTABLE_PACKAGE}/ present ({len(list(pkg.rglob('*.py')))} py files)")
    else:
        print("  Portable package missing in repo!")


def run_git_if_requested(changes: List[str], do_git: bool) -> None:
    if not do_git or not changes:
        return
    print("\n=== Git status after sync ===")
    try:
        subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, check=False)
        if input("Stage these changes? [y/N]: ").lower().startswith("y"):
            subprocess.run(["git", "add", "-u", "."], cwd=REPO_ROOT, check=False)
            subprocess.run(["git", "status", "--short"], cwd=REPO_ROOT, check=False)
    except Exception as e:
        print(f"Git operation failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Sync Perchance plugin between active Hermes and source repo")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--to-repo", action="store_true", help="Sync active Hermes → source repo (keep repo up to date)")
    group.add_argument("--to-active", action="store_true", help="Sync source repo → active Hermes (deploy)")
    group.add_argument("--both", action="store_true", help="Sync both directions")
    group.add_argument("--status", action="store_true", help="Show current differences")

    parser.add_argument("--dry-run", action="store_true", help="Preview changes only")
    parser.add_argument("--git", action="store_true", help="After --to-repo, offer to git add")
    parser.add_argument("--force", action="store_true", help="Skip confirmations")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.to_repo:
        print("Syncing from ACTIVE Hermes plugin → REPO (keeping source up to date)")
        if not args.force and not args.dry_run:
            if input("Continue? [y/N]: ").lower() != "y":
                print("Aborted.")
                return
        changes = sync_hermes_plugin_to_repo(dry_run=args.dry_run)
        run_git_if_requested(changes, args.git)

    elif args.to_active:
        print("Syncing from REPO → ACTIVE Hermes plugin")
        if not args.force and not args.dry_run:
            if input("This will overwrite active plugin files. Continue? [y/N]: ").lower() != "y":
                print("Aborted.")
                return
        sync_repo_to_hermes(dry_run=args.dry_run)

    elif args.both:
        if not args.force and not args.dry_run:
            if input("Bidirectional sync. Continue? [y/N]: ").lower() != "y":
                print("Aborted.")
                return
        sync_both(dry_run=args.dry_run)

    print("\nDone.")


if __name__ == "__main__":
    main()
