# Kronos Plugin Development Guide

Build your own skills, tool plugins, and provider plugins for Kronos and share them with the community.

---

## Plugin Types

| Type | What it does | Language |
|---|---|---|
| `skill` | Markdown workflow (index in context; full body via `skill_view` tool) | Markdown |
| `tool` | Executable Python tool the agent can call | Python |
| `provider` | LLM backend configuration | YAML |
| `mcp` | External MCP server tools (filesystem, fetch, GitHub, custom) | YAML config |

### Which extension should I build?

```
Need reusable instructions for the LLM?
  └─ skill (.md in ~/.kronos/skills/ or kronos skills install)

Need Python code the agent calls directly?
  └─ tool plugin (~/.kronos/plugins/tools/<name>/)

Need an external service with its own process (GitHub, filesystem, fetch)?
  └─ MCP server (kronos mcp add … — see docs/mcp.md)

Need a new LLM backend?
  └─ provider plugin (plugins/providers/)
```

---

## Skills (Markdown)

The simplest extension. Drop a `.md` file into `~/.kronos/skills/` and run `kronos skills reload` (or `:plugin reload` in-session).

Skills appear as a **compact index** in the system prompt. The agent loads full instructions on demand with the `skill_view` tool. Mark `inline: true` in frontmatter or `skill.yaml` to inject the full body every turn.

### Flat skill (simplest)

```
~/.kronos/skills/my_skill.md
```

Content format:

```markdown
# My Skill Title

## When to use
Describe the trigger: what user request should activate this skill.

## Workflow
1. Step one.
2. Step two.
3. Step three.

## Output
Describe the expected output format.
```

### Nested skill (with metadata)

```
~/.kronos/skills/my_skill/
├── SKILL.md        ← the workflow (required)
└── skill.yaml      ← metadata (optional)
```

`skill.yaml` format:

```yaml
name: my_skill
type: skill
version: "1.0.0"
description: "One-line description of what this skill does."
author: "Your Name"
tags: [research, writing, coding]
trust_level: community    # core | verified | community
trigger: "When user asks to summarize a meeting or document"
```

### Community plugin skills

Place in `~/.kronos/plugins/skills/<skill_name>/` for skills distributed as packages.

To sign a community skill for `verified` trust level:

```bash
# Generate HMAC signature (uses your local ~/.kronos/config/hmac_key.bin)
python - <<'EOF'
import hashlib, hmac
from pathlib import Path

key = Path.home().joinpath(".kronos/config/hmac_key.bin").read_bytes()
content = Path("SKILL.md").read_bytes()
sig = hmac.new(key, content, hashlib.sha256).hexdigest()
print(f"signature: {sig}")
EOF
```

Add the output to your `skill.yaml` as the `signature:` field.

---

## Tool Plugins (Python)

Adds a callable tool the agent can invoke with full ethics + approval gate enforcement.

### Directory layout

```
~/.kronos/plugins/tools/<plugin_name>/
├── plugin.yaml     ← required
└── tool.py         ← required
```

### `plugin.yaml`

```yaml
name: my_tool
type: tool
version: "1.0.0"
description: "Fetches data from My API."
author: "Your Name"
tags: [api, data]
trust_level: community
requires_approval: false
```

### `tool.py`

```python
from silex.tools.base import BaseTool

class MyTool(BaseTool):
    name = "my_tool"
    description = "Fetches data from My API."
    risk_level = "read_only"      # read_only | elevated | dangerous
    requires_approval = False

    schema = {
        "query": {"type": "string", "description": "What to look up"},
    }

    async def execute(self, query: str, **kwargs) -> str:
        # your logic here
        return f"Result for: {query}"
```

Hot-reload without restart:

```
/plugin reload
```

---

## Provider Plugins (YAML)

Override or extend the built-in LLM provider catalog.

Place in `~/.kronos/config/plugins/model-providers/<provider_name>/plugin.yaml`:

```yaml
name: my_provider
display_name: "My Custom Provider"
env_vars:
  - MY_PROVIDER_API_KEY
api_mode: chat_completions   # chat_completions | anthropic_native | gemini_native
base_url: "https://api.myprovider.com/v1"
description: "Custom OpenAI-compatible endpoint"
signup_url: "https://myprovider.com/signup"
fallback_models:
  - id: "my-model-v1"
    label: "My Model v1"
    tier: fast
    supports_images: false
    supports_structured_json: true
    context_window: 128000
    estimated_cost: low
```

No Python code needed. The provider is available immediately in `/model` selection.

---

## Installing Community Plugins

```
/plugin search <query>          # browse the catalog
/plugin install <name>          # install by catalog name
/plugin install https://...     # install from URL (.md for skill, .zip for tool)
/plugin uninstall <name>        # remove
/plugin reload                  # hot-reload all plugins and skills
```

---

## Trust Levels

| Level | Meaning |
|---|---|
| `core` | Bundled with Kronos — fully trusted |
| `verified` | HMAC signature validated against publisher key |
| `community` | No signature — shown with a warning in strict mode |

Set `KRONOS_MEMORY_GUARD_STRICT=1` to block `community` plugins from loading.

---

## Submitting to KronosHub

1. Fork the registry repository at `https://github.com/openyfai/kronos-hub`
2. Add your entry to `catalog.yaml` in the `entries:` list
3. Ensure `sha256` is set (run `sha256sum` on your file)
4. Open a pull request — core team reviews and sets `trust_level: verified` after audit

## Skill Audit Workflow (Security)

When submitting a skill for `verified` status, it undergoes the following audit workflow by the core team:

1. **Submission Review**: The PR is reviewed for malicious intent, prompt injection attempts, or insecure tool usage.
2. **Execution Test**: The skill is run in a strict `KRONOS_MEMORY_GUARD_STRICT=1` sandbox environment.
3. **Approval Gating Check**: The skill is verified to ensure it doesn't try to bypass `approval_required` flags for sensitive MCP/tool calls.
4. **HMAC Signing**: Once approved, the core team signs the `SKILL.md` file using the central KronosHub key and attaches the `signature` to the registry `catalog.yaml`. 
5. **Distribution**: The skill is officially marked as `verified` and users can install it safely.

---

## File Locations Reference

| Path | Purpose |
|---|---|
| `~/.kronos/skills/*.md` | Flat skill files |
| `~/.kronos/skills/<name>/SKILL.md` | Nested skill |
| `~/.kronos/plugins/skills/<name>/SKILL.md` | Community skill package |
| `~/.kronos/plugins/tools/<name>/` | Tool plugin directory |
| `~/.kronos/config/plugins/model-providers/<name>/` | Provider override |
| `~/.kronos/registry/catalog.yaml` | Local registry catalog |
| `https://kronos.openyf.dev/registry/catalog.yaml` | Remote KronosHub catalog |
| `https://kronos.openyf.dev/install.sh` | One-line installer (WSL2/Linux/macOS) |
| `~/.kronos/config/hmac_key.bin` | Local HMAC signing key |
