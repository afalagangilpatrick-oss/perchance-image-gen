# Perchance Free Image Generator Plugin for Hermes

**Free, no-account text-to-image inside Hermes** using Perchance.org's direct API.

This plugin adds a reliable "perchance" provider that works in chat and via a rich CLI.

## Quick Start

1. Install the plugin:
   ```bash
   hermes plugins install ~/perchance-hermes-plugin --enable
   ```

2. Get a key (easiest ways):
   ```bash
   hermes perchance key fetch                 # automatic (best effort)
   hermes perchance key fetch --visible       # show browser if Cloudflare blocks
   python ~/.hermes/plugins/image_gen/perchance/fetch_perchance_key.py
   ```

3. Use it:
   - In chat: `generate a cyberpunk cat in neon rain`
   - CLI: `hermes perchance generate "your prompt here" --aspect landscape`

Images are saved to `~/.hermes/cache/images/`.

## Features

- Completely free (rate-limited, no signup)
- Aspect ratios + direct resolution control
- Guidance scale, negative prompts, seed
- Multiple images per call (`--count`)
- Automatic key caching + validation
- Best-effort automatic key fetching with Playwright
- Rich CLI (status, generate, recent images, cache clearing, etc.)
- Works seamlessly inside Hermes chat / tools
- Standalone helper script

## Installation

### From the packaged repo (recommended)
```bash
hermes plugins install ~/perchance-hermes-plugin --enable
```

### From Git (once you publish it)
```bash
hermes plugins install yourname/perchance-hermes-plugin --enable
```

After install or changes, restart Hermes or reload tools.

## Getting a userKey

Perchance requires a `userKey` (64 hex chars) obtained from a real browser session because of Cloudflare protection.

### Automatic methods (recommended first)
```bash
hermes perchance key fetch
hermes perchance key fetch --visible --browser firefox
python fetch_perchance_key.py --visible
```

The improved Playwright fetcher:
- Handles iframes (common on Perchance pages)
- Tries multiple button selectors
- Listens for both GET and POST requests
- Verifies the key using Perchance's check endpoint
- Falls back between Chromium and Firefox

### Manual method (most reliable)
1. Visit https://perchance.org/ai-text-to-image-generator in Chrome or Firefox
2. Open DevTools (F12) → **Network** tab
3. Enter any prompt and click **Generate**
4. Click the request to `https://image-generation.perchance.org/api/generate`
5. Copy the `userKey` parameter value (exactly 64 hexadecimal characters)
6. Set it:
   ```bash
   hermes perchance key set THE_KEY_HERE
   # or
   export PERCHANCE_USER_KEY=THE_KEY_HERE
   ```

Keys eventually expire. When one stops working, repeat the process.

## CLI Reference

```bash
hermes perchance --help
```

### Key Management
- `hermes perchance key get`
- `hermes perchance key set <64-hex-key>`
- `hermes perchance key clear`
- `hermes perchance key fetch [--visible] [--browser chromium|firefox]`
- `hermes perchance key validate`

### Generation
```bash
hermes perchance generate "a majestic dragon flying over mountains" \
  --aspect landscape \
  --resolution 1536x1024 \
  --guidance 8 \
  --negative "blurry, low quality, text" \
  --seed 12345 \
  --count 3 \
  --open \
  --save-dir ~/Pictures/perchance
```

**Options:**
- `--aspect`, `-a` : landscape | square | portrait
- `--resolution`, `-r` : direct override (e.g. 512x768)
- `--guidance`, `-g` : 1–30 (default 7)
- `--negative`, `-n`
- `--seed`
- `--count`, `-c`, `--num` : generate multiple
- `--out`, `-o` : specific output path
- `--save-dir` : custom directory
- `--open` : open image(s) after generation
- `--quiet`, `-q`

### Other Commands
- `hermes perchance status`
- `hermes perchance models`
- `hermes perchance test`
- `hermes perchance config`
- `hermes perchance recent` / `images` / `list` [--limit 10]
- `hermes perchance clear-cache [--keys] [--images]`
- `hermes perchance open` / `web`

Standalone helper:
```bash
python fetch_perchance_key.py --visible
```

## Usage Inside Hermes

Once a valid key is configured, just ask naturally:

> generate an image of a cozy cabin in the snow at night, warm lights, cinematic

> make a portrait of a cyberpunk samurai, detailed, high quality

The provider is automatically selected if set as default or if it's the only available one.

Set as default provider:
```yaml
# ~/.hermes/config.yaml
image_gen:
  provider: perchance
```

## How the Automation Works

- On `is_available()` and before every generation, the plugin calls `_auto_ensure_key()`
- It checks env → config → cache, then validates the key
- On failure (missing/expired/invalid), it attempts an automatic Playwright fetch
- On "invalid_key" responses during generation, it clears the bad key and tries one auto-refresh

**Playwright improvements** (2026 update):
- Iframe content frame support
- Multiple realistic selectors from community reverse-engineering
- POST data extraction
- Verification endpoint check
- Visible mode + browser fallback (Chromium ↔ Firefox)
- Better timeouts and anti-detection args

## Troubleshooting

**"auth_required" or no key**
→ Run `hermes perchance key fetch --visible`

**Cloudflare "Just a moment..." blocks**
→ Use `--visible` flag or do the manual DevTools method in a normal browser.

**Key suddenly stops working**
→ Keys expire. Clear with `hermes perchance key clear` and fetch a new one.

**Playwright not installed**
```bash
pip install playwright
playwright install chromium
```

**Images not opening automatically**
Make sure `xdg-open` (Linux) or `open` (macOS) works in your terminal.

**Low quality or unexpected results**
- Increase `--guidance` (higher = more prompt adherence)
- Use better negative prompts
- Try different seeds

## Packaging & Catalog Metadata

The plugin includes a rich `plugin.yaml` so it can appear nicely in the Hermes catalog:

- `kind: image-gen`
- Tags, capabilities, badge="free"
- Setup instructions
- Homepage and version info

This enables discoverability, nice listings, and future one-click install from `hermes plugins search`.

## Standalone Helper Script

`fetch_perchance_key.py` can be run completely outside Hermes. It contains the same improved fetch logic plus clear fallback instructions.

## Limitations

- Free service → rate limits and occasional downtime
- Text-to-image only (no image-to-image or reference images in this provider)
- Resolution is relatively low compared to paid models
- Requires occasional key refresh due to Cloudflare

## Credits & Sources

- Reverse-engineered API from community projects (aein00/perchance-image-generator, eeemoon/perchance, etc.)
- Playwright patterns refined for Perchance's iframe + Cloudflare setup
- Hermes plugin architecture

---

Enjoy free image generation inside Hermes! 

For the absolute latest version or to contribute improvements, see the plugin repo.