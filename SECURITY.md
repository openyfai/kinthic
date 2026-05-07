# Security Policy

ARIA is a local AI agent that can read files, browse the web, and, when enabled, execute terminal or code-edit actions. Treat it as powerful local software, not a passive chatbot.

## Default Security Posture

By default ARIA should run with:

- tool approvals enabled
- terminal execution disabled
- direct code application disabled
- background actions disabled
- web API key required for non-loopback binds
- Telegram deny-by-default until paired

## Threat Model

High-risk areas:

- terminal execution
- code editing or repo writes
- browser/network actions
- Telegram access from unpaired users
- remote web exposure without authentication
- multi-process access to the same local SQLite brain

## Deployment Guidance

- Keep `ARIA_WEB_HOST=127.0.0.1` unless you explicitly need remote access.
- If you bind beyond loopback, set `ARIA_WEB_API_KEY`.
- Prefer one writer process per data directory.
- Pair Telegram with `aria telegram pair` instead of enabling public mode.
- Review pending tool approvals before allowing high-impact actions.

## Reporting Security Issues

Please do not open a public issue for exploitable vulnerabilities that could affect users running ARIA locally or remotely.

Instead, share:

- affected version or commit
- reproduction steps
- expected vs actual behavior
- impact assessment
- suggested mitigation, if known

Preferred path: use GitHub private vulnerability reporting for this repository if it is enabled.

If private reporting is not available yet, contact the maintainers at `security@aria.local` and avoid posting proof-of-concept details publicly.

If you are maintaining a fork, audit your own deployment defaults as well.
