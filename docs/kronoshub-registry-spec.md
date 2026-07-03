# KronosHub Registry API Specification

**Host:** `https://kronos.openyf.dev`  
**Version:** 1.0  
**Status:** Design spec (Phase 3)

This document defines the remote catalog format served at `https://kronos.openyf.dev/registry/catalog.yaml` and consumed by `silex/plugins/registry.py` via `:plugin search` / `:plugin install`.

---

## Endpoints

| URL | Method | Purpose |
|---|---|---|
| `/install.sh` | GET | One-line installer (`curl -fsSL … \| bash`). WSL2/Linux/macOS only. |
| `/registry/catalog.yaml` | GET | Full plugin & skill catalog |
| `/registry/catalog.yaml` | HEAD | ETag / Last-Modified for cache validation |

No authentication required for read access. Write access is via GitHub PR to the `openyfai/kronos-hub` repository (future).

---

## Catalog Schema

```yaml
version: "1.0"
generated_at: "2026-06-05T12:00:00Z"
entries:
  - name: tell_joke
    type: skill          # skill | tool | provider
    version: "1.0.0"
    description: "Dry, sarcastic joke delivery workflow"
    author: "OpenYF"
    tags: [humor, bundled]
    trust_level: core    # core | verified | community
    source: bundled
    url: ""              # empty for bundled-only entries
    sha256: ""           # hex digest of download artifact (required for remote)
    entry_file: tell_joke.md
    installed: false     # client-side flag; ignored in remote catalog
```

### Required fields

| Field | Type | Notes |
|---|---|---|
| `name` | string | Unique identifier; matches install folder / skill stem |
| `type` | enum | `skill`, `tool`, or `provider` |
| `version` | semver string | |
| `description` | string | Max 200 chars recommended |
| `trust_level` | enum | `core`, `verified`, `community` |

### Optional fields

| Field | Type | Notes |
|---|---|---|
| `author` | string | Display name or org |
| `tags` | string[] | Used by `:plugin search` |
| `url` | string | HTTPS download URL (`.md` for skills, `.zip` for tools) |
| `sha256` | string | SHA-256 hex of artifact bytes; enforced on install |
| `signature` | string | HMAC-SHA256 of artifact for `verified` trust |
| `entry_file` | string | Filename inside the package |
| `requires_approval` | bool | Tool plugins only |
| `min_kronos_version` | semver | Compatibility gate |

---

## Artifact Formats

### Skills (`type: skill`)

- Single `.md` file served at `url`
- Installed to `~/.kronos/skills/<name>.md`
- Optional `skill.yaml` sidecar in nested packages

### Tool plugins (`type: tool`)

- `.zip` archive containing:
  ```
  <name>/
  ├── plugin.yaml
  └── tool.py
  ```
- Installed to `~/.kronos/plugins/tools/<name>/`
- Extracted and hot-reloaded via `:plugin reload`

### Provider plugins (`type: provider`)

- `plugin.yaml` only (no Python required)
- Installed to `~/.kronos/config/plugins/model-providers/<name>/`

---

## Client Refresh Flow

```
:plugin search <query>     → reads ~/.kronos/registry/catalog.yaml (local)
:plugin install <name>     → looks up entry, downloads url, verifies sha256
```

Background refresh (optional, triggered manually or on daemon start):

```python
registry.refresh_from_remote()  # merges new entries; never overwrites local installed flags
```

Environment override:

```bash
export KRONOS_REGISTRY_URL=https://kronos.openyf.dev/registry/catalog.yaml
```

---

## Submission Process (Community)

1. Fork `https://github.com/openyfai/kronos-hub`
2. Add entry to `catalog.yaml` with `sha256` of your artifact
3. Upload artifact to `releases/` or provide a stable HTTPS URL
4. Open PR — maintainers audit and set `trust_level: verified` after review
5. Community entries without audit ship as `trust_level: community`

---

## Install Surface (not PyPI)

Kronos is distributed exclusively via:

```bash
curl -fsSL https://kronos.openyf.dev/install.sh | bash
```

**Windows:** Native cmd/PowerShell is blocked. Users must install WSL2 and run the command inside a Linux terminal (Ubuntu).

The installer:
- Creates `~/.kronos/` directory tree
- Installs Python deps into `~/.kronos/runtime/venv/` via `uv`
- Registers `kronos` CLI in `~/.kronos/bin/`
- Seeds bundled skills and KronosHub catalog
- Writes `~/.kronos/.env` template for API keys and messaging tokens
