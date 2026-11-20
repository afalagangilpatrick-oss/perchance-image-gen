# Perchance Image Generator Plugin for Hermes

Free, no-account text-to-image generation for Hermes using Perchance.org.

## Features

- **Free text-to-image** via Perchance's direct API (no signup, no cost)
- Full aspect ratio support: `landscape`, `square`, `portrait`
- Custom guidance scale and negative prompts
- Smart userKey management:
  - Environment variable `PERCHANCE_USER_KEY`
  - Config under `image_gen.perchance.user_key`
  - Automatic caching of last working key (with invalidation)
- **Automation for key fetching**:
  - `hermes perchance key fetch` (best-effort using Playwright if installed)
  - Automatic checking + refresh attempts when the provider is called (`is_available`, generate)
  - Falls back gracefully to manual instructions
- Robust error handling (Cloudflare blocks, expired keys, etc.)
- Saves images locally with metadata
- **Rich CLI helper**: `hermes perchance ...` (status, key management, generate with many options, test, config, models, open)
- Works inside Hermes chat ("generate an image of...") once configured
- Single model: `perchance-ai-text-to-image`

## Limitations

- Text-to-image only (no image editing or reference images)
- Requires a `userKey` obtained from a real browser session (Cloudflare protection)
- English prompts work best
- Rate-limited and keys can expire

## Installation

### From local directory (recommended for now)
```bash
hermes plugins install /path/to/this/repo --enable
```

### From Git (once published)
```bash
hermes plugins install afalagangilpatrick-oss/perchance-image-gen --enable
```

After install, configure a key (see below).

## What "more metadata for the catalog" means

Hermes has a plugin catalog system (`hermes plugins search`, `hermes plugins show`, `hermes plugins install name`).

A `plugin.yaml` (or manifest) file provides structured metadata so the plugin appears nicely in the catalog:

- `name`, `version`, `description`, `author`, `license`, `homepage`
- `kind` or `category` (e.g. image-gen)
- `tags`, `capabilities`, `badge`
- `setup` instructions (key name, prompt, URL)
- `min_hermes_version`, `requires`
- `entry` point

This enables:
- Discoverability in `hermes plugins search`
- Pretty listings with badges and descriptions
- Automatic setup prompts in `hermes tools` or first use
- Version pinning and dependency checks
- Better UX in TUI, gateway, and docs

We expanded `plugin.yaml` with these fields so the Perchance plugin can be published to the catalog in the future.

## Configuration

Get a key:
1. Visit https://perchance.org/ai-text-to-image-generator
2. DevTools → Network → Generate something
3. Copy the `userKey` from an `/api/generate` request (64 hex chars)

Then set it:
```bash
hermes perchance key set <the-key>
```

Or via env / config.yaml.

Set as default provider (optional):
```yaml
# ~/.hermes/config.yaml
image_gen:
  provider: perchance
```

## CLI Usage

```bash
hermes perchance status                 # Check key and availability
hermes perchance key get
hermes perchance key set <64-hex-key>
hermes perchance key clear
hermes perchance generate "prompt here" --aspect square --guidance 8
hermes perchance open                    # Open the web generator
```

## In Chat

Once a valid key is configured:
> generate a cyberpunk cat wearing sunglasses, neon city background

The image will be generated and delivered through your normal Hermes image flow.

## Development / Packaging

This repo follows Hermes plugin conventions for image_gen providers + CLI registration.

To test locally:
- Place in `~/.hermes/plugins/image_gen/perchance/` or install via the command above.

## License

MIT (or whatever you choose). Perchance service terms still apply to generated images and usage.