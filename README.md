# Perchance Image Generator

**Free, no-account text-to-image for terminals and Python scripts.**

Generates images using Perchance.org's direct API. Works great in any terminal-based AI/agent setup ("konsole esque" tools).

## Quick Start (Standalone)

```bash
# Install
pip install git+https://github.com/afalagangilpatrick-oss/perchance-image-gen.git

# Or from local
pip install -e .

# Get a key (one time)
perchance-key-fetch
# or with visible browser:
perchance-key-fetch --visible

# Generate
perchance-gen "a cyberpunk cat in neon rain, detailed"
```

Python API:
```python
from perchance_image_gen import PerchanceGenerator, generate_image

result = generate_image("cozy cabin in the snow")
if result["success"]:
    print("Saved to:", result["image"])
```

## Features

- Completely free
- Good CLI and clean Python API
- Automatic key fetching (Playwright, optional but excellent)
- Key caching + validation + auto-refresh on failure
- Aspect ratios, guidance, negative prompts, seeds, custom resolution
- Works in any Python environment or terminal agent

## For Hermes Users

See the full guide: [PERCHANCE_HERMES_PLUGIN_GUIDE.md](PERCHANCE_HERMES_PLUGIN_GUIDE.md)

Install as Hermes plugin:
```bash
hermes plugins install . --enable
```

The Hermes-specific registration lives in `plugins/image_gen/perchance/`.

## For Other Terminal / Agent Systems

This package is designed to be dropped into other console-style AI tools.

1. `pip install -e .` (or from git)
2. Use the CLI or import the class.
3. The only external optional dependency is `playwright` for automatic key fetching.

You can also copy `perchance_image_gen/core.py` and `key_fetcher.py` into your project if you prefer zero dependencies beyond `requests`.

## Getting a Key

The service requires a `userKey` obtained from a browser (Cloudflare protection).

**Recommended:**
```bash
perchance-key-fetch --visible
```

**Manual:**
1. Go to https://perchance.org/ai-text-to-image-generator
2. DevTools → Network → Generate
3. Copy the `userKey` from the `/api/generate` request
4. `export PERCHANCE_USER_KEY=...` or let the tool cache it

## Packaging & Publishing

This repo is structured as a proper Python package:

- `pyproject.toml` with console scripts
- Clean `perchance_image_gen/` package (no framework lock-in)
- Hermes plugin kept separate under `plugins/`

To publish:
1. Update version in `pyproject.toml` and `__init__.py`
2. `pip install build twine`
3. `python -m build`
4. `twine upload dist/*`

For Hermes catalog: the `plugins/image_gen/perchance/plugin.yaml` provides rich metadata.

## Development & Keeping the Repo Up to Date

When developing, you often edit the plugin inside Hermes (in `~/.hermes/plugins/image_gen/perchance/`).

This repo includes automation to keep the **source repo** in sync with your live edits.

### Quick Sync

From the repo root:

```bash
# Push live Hermes changes back to the source repo (most common)
./scripts/sync.sh --to-repo

# Or the Python version
python scripts/sync.py --to-repo --git     # also offers to git add

# Deploy repo changes to active Hermes
./scripts/sync.sh --to-active

# See what's different
./scripts/sync.sh --status
```

### Continuous Watching (during heavy development)

```bash
# Poll for changes and auto-sync to repo
python scripts/watch_sync.py

# (Better) install watchdog for efficient watching
pip install watchdog
python scripts/watch_sync.py
```

### Recommended Workflow

1. Make changes inside Hermes (chat or by editing the active plugin files directly).
2. Run `./scripts/sync.sh --to-repo --git`
3. Review, commit, and push from the repo.
4. (Optional) Run `./scripts/sync.sh --to-active` on other machines after pulling.

### Setting up a Cron / Scheduled Sync (Hermes)

You can add a simple cron inside Hermes:

```bash
# Example (run every 15 minutes)
hermes cron add --name perchance-sync \
  --command "cd ~/perchance-hermes-plugin && python scripts/sync.py --to-repo --force" \
  --schedule "*/15 * * * *"
```

### Git Hooks (advanced)

You can also add a post-commit hook or use a tool like `entr` or `fswatch` to trigger sync.

## License

MIT

Perchance service terms still apply to usage and generated images.