#!/usr/bin/env python3
"""
Simple file watcher for the Perchance plugin.

Watches the active Hermes plugin directory and automatically syncs
changes to the source repo.

Usage:
    python scripts/watch_sync.py
    python scripts/watch_sync.py --interval 5   # poll every 5 seconds

Requires no extra packages (uses polling).

For real file watching, install:
    pip install watchdog
    Then it can use inotify-style events.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.resolve()
ACTIVE = Path.home() / ".hermes" / "plugins" / "image_gen" / "perchance"
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync.py"


def try_watchdog():
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class Handler(FileSystemEventHandler):
            def __init__(self):
                self.last_sync = 0

            def on_any_event(self, event):
                if event.is_directory:
                    return
                now = time.time()
                if now - self.last_sync > 2:  # debounce
                    self.last_sync = now
                    print(f"Change detected: {event.src_path}")
                    self._sync()

            def _sync(self):
                try:
                    subprocess.run(
                        [sys.executable, str(SYNC_SCRIPT), "--to-repo", "--force"],
                        cwd=REPO_ROOT,
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    print("  → Synced to repo")
                except Exception as e:
                    print(f"  Sync error: {e}")

        observer = Observer()
        observer.schedule(Handler(), str(ACTIVE), recursive=True)
        observer.start()
        print(f"Watching {ACTIVE} (using watchdog)...")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
        return True
    except ImportError:
        return False


def polling_watcher(interval: float = 3.0):
    print(f"Polling watcher (every {interval}s). Install 'watchdog' for better performance.")
    print(f"Watching: {ACTIVE}")
    print("Press Ctrl+C to stop.\n")

    last_mtimes = {}

    try:
        while True:
            if not ACTIVE.exists():
                time.sleep(interval)
                continue

            changed = False
            for p in ACTIVE.rglob("*"):
                if p.is_file() and "__pycache__" not in str(p):
                    try:
                        mtime = p.stat().st_mtime
                        if p not in last_mtimes or mtime > last_mtimes[p]:
                            last_mtimes[p] = mtime
                            changed = True
                    except Exception:
                        pass

            if changed:
                print("Changes detected in active plugin...")
                try:
                    result = subprocess.run(
                        [sys.executable, str(SYNC_SCRIPT), "--to-repo", "--force"],
                        cwd=REPO_ROOT,
                        capture_output=True,
                        text=True,
                    )
                    print(result.stdout.strip() or "Synced.")
                except Exception as e:
                    print(f"Sync failed: {e}")

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nWatcher stopped.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=3.0, help="Polling interval in seconds")
    args = parser.parse_args()

    if not try_watchdog():
        polling_watcher(args.interval)


if __name__ == "__main__":
    main()
