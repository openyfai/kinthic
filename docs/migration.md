# Kronos Migration Guide

Kronos provides a built-in migration tool to safely import your skills, personas, and configurations from other agent frameworks like **Hermes** and **OpenClaw**.

## How it works

The `kronos migrate` tool scans your existing framework's configuration directory, identifies migratable assets, and imports them into your `~/.kronos` directory. 

**Imported Skills Trust**: All imported skills are explicitly marked as `community` trust (not `core`), ensuring they adhere to Kronos's strict security sandboxing and do not inherit elevated privileges by default.

**Secrets Migration**: Hermes `.env` files are parsed and imported into the `secrets.json` file in Kronos.

## Hermes Migration

Hermes typically stores its configuration in `~/.hermes/`. Kronos will scan for:
- `config.yaml`
- `.env` (API keys)
- `skills/` directory
- `memories/USER.md` (Persona identity)

**Commands:**
```bash
# 1. Scan the Hermes directory to see what will be migrated
kronos migrate scan --from hermes

# 2. Perform a dry-run to ensure there are no conflicts
kronos migrate import --from hermes --dry-run

# 3. Apply the migration
kronos migrate import --from hermes --apply
```

## OpenClaw Migration

OpenClaw stores its configuration in `~/.openclaw/`. Kronos will scan for:
- `openclaw.json` (General settings and allowlists)
- `workspace/` directory (Markdown skills and `SOUL.md` identity)

**Commands:**
```bash
# 1. Scan the OpenClaw directory
kronos migrate scan --from openclaw

# 2. Perform a dry-run
kronos migrate import --from openclaw --dry-run

# 3. Apply the migration
kronos migrate import --from openclaw --apply
```

## Post-Migration Security Check

After successfully importing data, **you must re-pair your Telegram account**.
This ensures the imported configuration doesn't accidentally grant unauthorized access.

1. Start Kronos: `kronos telegram`
2. Open Telegram and send: `/pair`
3. Enter your secret passcode.
