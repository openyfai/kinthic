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

## Security-Relevant Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ARIA_WORKSPACE` | Current directory | Sandbox boundary for file reads/writes |
| `ARIA_ENABLE_CODE_APPLY` | `false` | Auto-approve code edits (ethics engine still runs) |
| `ARIA_ENABLE_TERMINAL_EXECUTION` | `false` | Allow terminal command execution |
| `ARIA_REQUIRE_TOOL_APPROVALS` | `true` | Require human approval for destructive tools |
| `ARIA_WEB_API_KEY` | (none) | Required when binding to non-loopback addresses |
| `ARIA_WS_MAX_MESSAGE_CHARS` | `2000000` | Maximum WebSocket message size (bytes) |
| `ARIA_GOAL_COOLDOWN_SECONDS` | `600` | Minimum seconds between goal state transitions |

## Known Limitations

### DNS Rebinding in Browser Tool

**Status:** Documented, backlogged. Low risk for local deployments.

The browser tool validates URLs by resolving the hostname and checking that all IP addresses are public (not private, loopback, or link-local). However, there is a time-of-check-to-time-of-use (TOCTOU) gap: the DNS could resolve differently between validation and the actual Playwright request.

An attacker with control of a DNS server could exploit this to make ARIA browse internal network services (a DNS rebinding attack).

**Why the risk is low:**
- ARIA binds to loopback by default — the attacker needs local access.
- The LLM chooses which URLs to browse, and the ethics engine evaluates the intent.
- The attack requires a malicious DNS server and a prompt injection that tricks the LLM into visiting the attacker's domain.

**Future fix:** Pin the resolved IP address and pass it to Playwright using `--host-resolver-rules` to enforce the validated address at the transport layer.

### API Key Storage on Windows

**Status:** Documented, warning implemented.

On Windows, `data/secrets.json` has no file permission protection because Windows does not support Unix `chmod`. Any process running as the current user can read the file.

**Mitigation:** ARIA logs a warning on Windows recommending environment variables (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.) over the secrets file.

### Approval Re-Execution Without Re-Validation

**Status:** Documented, backlogged. Non-issue in single-user mode.

When a user approves a pending tool action, the tool executes with the original arguments without re-checking ethics. In theory, if the database is writable by another process, the arguments could be modified between queuing and approval.

**Why the risk is low:** This only matters if the SQLite database is shared with another writer process, which is not the default configuration.

**Future fix:** Re-validate arguments and re-run the ethics check before executing approved tools.

## Audit History

| Version | Date | Findings Fixed |
|---------|------|----------------|
| v1.0.4 | 2026-05-10 | Shell injection in `aria stop`, file reader sandbox escape, silent Telegram failures, Docker event loop blocking |
| v1.0.5 | 2026-05-10 | Code editor ethics bypass, code editor sandbox scope, remaining `shell=True` calls, non-Gemini provider resilience, WebSocket size limits, usage tracker key collisions, history truncation, goal loop token burn, PROJECT_ROOT centralization |

