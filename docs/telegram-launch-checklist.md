# Kinthic pre-launch checklist (Telegram-first)

Use this as a gate before public announcement. **Telegram is the primary chat interface** — security and pairing come first, then reliability, then polish.

Related docs: [quickstart](quickstart.md) · [WSL setup](wsl-setup.md) · [MCP](mcp.md) · [SECURITY.md](../SECURITY.md)

---

## Priority legend

| Priority | Meaning |
|----------|---------|
| **P0** | Block launch if any item fails |
| **P1** | Should pass before marketing Telegram as primary |
| **P2** | Nice to have; can ship shortly after launch |

---

## P0 — Block launch if any fail

### 1. Fresh install → Telegram golden path

Run on a **clean WSL2 Ubuntu VM** (not your dev machine):

- [ ] `curl -fsSL https://kinthic.openyf.dev/install.sh | bash` completes without error
- [ ] `kinthic` CLI exists after `source ~/.bashrc`
- [ ] `kinthic onboard` completes: provider ping OK, 5 core skills installed
- [ ] During onboard: Telegram pairing succeeds (deep link or `/start PAIR-…`)
- [ ] `kinthic doctor` shows: setup complete, provider key OK, **≥1 paired Telegram user**
- [ ] `kinthic doctor --ping` returns `[ok]`
- [ ] `kinthic telegram run` starts and prints **pairing active** (not public mode, not empty deny list with no pairs)

**Success criteria:** First working Telegram reply in under ~20 minutes, without reading `PLUGIN_DEVELOPMENT.md`.

```bash
curl -fsSL https://kinthic.openyf.dev/install.sh | bash
source ~/.bashrc
kinthic onboard
kinthic telegram run
```

---

### 2. Telegram access control (security)

Default must be **deny-by-default, paired users only**.

- [ ] `TELEGRAM_PUBLIC_MODE` is **unset or `false`** in `~/.kinthic/.env`
- [ ] `kinthic doctor` does **not** show public mode enabled
- [ ] Unpaired Telegram account gets **Access Denied** (not a cognitive reply)
- [ ] Pairing works via all documented paths:
  - [ ] `kinthic telegram pair` → user sends `PAIR-…` or `/pair CODE`
  - [ ] `/start CODE` deep link from `kinthic onboard`
  - [ ] Optional legacy: `ALLOWED_TELEGRAM_USERS=<id>` in `.env`
- [ ] `/logout` revokes access; next message is denied
- [ ] Bot token never appears in bot replies or public logs
- [ ] `~/.kinthic/.env` and `~/.kinthic/config/secrets.json` are **not** committed to git

On startup, `kinthic telegram run` should print one of:

- `🔒 Whitelist active: …` (env allowlist)
- `🔒 Pairing active: N Telegram user(s) authorized.` ← **target for launch**
- `🔒 Deny-by-default: generate a pairing code…` (OK before first pair, not OK in prod)

**Never acceptable in production:**

- `⚠️  PUBLIC MODE: Any Telegram user can interact with Kinthic!`

Implementation reference: `silex/adapters/telegram.py` → `_print_security_status()`.

---

### 3. Tool safety defaults

Telegram users can trigger tools remotely. Verify defaults match [SECURITY.md](../SECURITY.md):

| Setting | Launch value | Verify with `kinthic doctor` |
|---------|--------------|----------------------------|
| Tool approvals | **ON** | `Approvals required: True` |
| Terminal execution | **OFF** | disabled |
| Code apply | **OFF** | disabled |
| Browser actions | OFF for safest v1 (your choice) | matches intent |
| Background loop | **OFF** for v1 Telegram | no surprise autonomous jobs |

Manual tests **in Telegram** (as paired user):

- [ ] Web search request → works or fails gracefully
- [ ] “Run `rm -rf`” / shell command → blocked or requires approval (not silent auto-run)
- [ ] File edit request → enters approval queue, not instant write
- [ ] MCP write tools (if enabled) → respect `requires_approval` in `~/.kinthic/config/mcp.yaml`

---

### 4. Approval workflow on Telegram

Risky tools wait up to **120 seconds** for operator approval in the DB. Telegram exposes:

- `/approvals` — list pending
- `/approve <id-prefix>` — approve
- `/reject <id-prefix>` — reject

End-to-end test:

- [ ] Trigger a tool that needs approval (e.g. code edit with approvals on)
- [ ] Within 120s, `/approvals` shows the pending item
- [ ] `/approve <prefix>` → tool completes; user gets follow-up context in reply
- [ ] `/reject <prefix>` → agent explains refusal; no side effects
- [ ] No approval within 120s → turn times out cleanly (no hang, no partial writes)

**Launch decision:** Either document “when Kinthic pauses, run `/approvals`” in quickstart, or implement proactive approval push before marketing Telegram as primary (see [Known gaps](#known-gaps-and-launch-risks)).

---

### 5. Secrets and process isolation

- [ ] Separate @BotFather tokens for dev vs production
- [ ] Provider API keys only in `~/.kinthic/.env` or secrets store — never in repo
- [ ] Do **not** run TUI (`kinthic`) and `kinthic telegram run` against the same brain without understanding SQLite single-writer risk
- [ ] For 24/7, pick **one** process model and test restart:
  - [ ] `kinthic telegram run` (simple), or
  - [ ] `kinthic daemon` (watchdog) — survives kill -9 and restarts cleanly

---

## P1 — Telegram product quality

### 6. Message UX

- [ ] Short replies render correctly (Markdown)
- [ ] Long replies (>4096 chars) — test verbose answer; confirm behavior (see gaps — no auto-split today)
- [ ] Broken Markdown falls back to plain text (adapter already tries this)
- [ ] “typing…” indicator appears before slow replies
- [ ] Internal errors show user-safe message, not stack traces

---

### 7. Bot commands

Test each as a **paired** user:

| Command | Expected |
|---------|----------|
| `/start` | Friendly intro + Telegram ID |
| `/whoami` | Shows user ID (support/debug) |
| `/status` | Provider, model, session |
| `/skills` | Lists loaded skills |
| `/approvals` | Pending tool approvals |
| `/approve` / `/reject` | Resolves approval by ID prefix |
| `/logout` | Unpairs account |

- [ ] @BotFather command list matches README / quickstart
- [ ] Undocumented commands don’t leak sensitive data

---

### 8. Onboard → Telegram story

- [ ] README and [quickstart](quickstart.md) lead with: install → **`kinthic onboard`** → **`kinthic telegram run`**
- [ ] `telegram_setup` skill installed after onboard
- [ ] `.env.example` documents pairing (not public mode)
- [ ] 2–3 min demo recorded: install → onboard → Telegram joke → `/status`

---

## P1 — Infrastructure

### 9. Hosted assets

- [ ] `https://kinthic.openyf.dev/install.sh` serves current `scripts/install.sh`
- [ ] `https://kinthic.openyf.dev/registry/catalog.yaml` live (offline install still works via bundled catalog)
- [ ] GitHub release includes `kinthic-ui-linux-x64` **or** install script shows clear UI build instructions

Spec: [kinthichub-registry-spec.md](kinthichub-registry-spec.md)

---

### 10. Docker Telegram (optional)

**Verify before recommending Docker** — compose file mounts `./data` but Kinthic defaults to `~/.kinthic` inside the container.

- [ ] `docker compose --profile telegram up` persists brain + paired users
- [ ] Token and keys load from mounted `.env`
- [ ] Container restart keeps memory and pairing
- [ ] **Or** document WSL native install only for v1 and omit Docker from quickstart

---

### 11. CI and smoke tests

- [ ] `python -m pytest tests/` green on main
- [ ] Fresh install smoke: `kinthic doctor`, `kinthic skills list`, `kinthic mcp list`
- [ ] `tests/test_security_fixes.py` passes

---

## P2 — Post-launch polish

### 12. MCP (optional for Telegram v1)

- [ ] Filesystem preset scoped to workspace only (`WORKSPACE_DIR`)
- [ ] `requires_approval` includes write tools in `mcp.yaml`
- [ ] `kinthic mcp test filesystem` passes where `npx` is available
- [ ] `kinthic doctor` MCP section shows no risky combos (fetch + terminal + code apply all on)

See [mcp.md](mcp.md).

---

### 13. Skills

- [ ] `kinthic skills list` shows core skills after onboard
- [ ] “Tell me a joke” works via progressive `skill_view` loading
- [ ] Edit `~/.kinthic/skills/*.md` → reload → change visible in session

---

### 14. Marketing and trust

- [ ] Replace placeholder assets with Telegram onboarding GIF/screenshots
- [ ] SECURITY.md linked from README
- [ ] “Not public mode by default” stated clearly on homepage
- [ ] Support playbook: pairing fails → check ID, expired code (10 min TTL), invalid token

---

## Recommended launch profile (Telegram-primary, secure)

Use this posture in docs and your production `.env`:

```env
GEMINI_API_KEY=...
TELEGRAM_BOT_TOKEN=...

# Never enable for public launch:
# TELEGRAM_PUBLIC_MODE=false

# Prefer pairing over static allowlist:
# ALLOWED_TELEGRAM_USERS=

# Safe defaults — enable only deliberately:
# ARIA_ENABLE_TERMINAL_EXECUTION=false
# ARIA_ENABLE_CODE_APPLY=false
# ARIA_REQUIRE_TOOL_APPROVALS=true
# ARIA_ENABLE_BROWSER_ACTIONS=false
# ARIA_ENABLE_BACKGROUND_LOOP=false
```

**Recommended runtime:** one machine, one `kinthic telegram run`, one paired operator, approvals on, terminal and code apply off.

---

## 30-minute pre-launch drill

Run once on a clean WSL VM:

1. Install → `kinthic onboard` (with Telegram pairing)
2. `kinthic telegram run` → send “hi”, “tell me a joke”, “search for …”
3. Trigger approval → `/approvals` → `/approve`
4. Second phone / unpaired account → confirm **Access Denied**
5. `/logout` → confirm denied
6. `kinthic doctor --ping`
7. Kill bot process → restart → session/memory still sane

If step 3 feels broken (user doesn’t know to run `/approvals`), treat as a **launch blocker** for Telegram-primary positioning—or narrow the tool surface to read-only for v1.

---

## Known gaps and launch risks

| Gap | Impact | Workaround / fix |
|-----|--------|------------------|
| **No push when tool approval queued** | User thinks bot is stuck mid-turn | Document `/approvals`; or implement Telegram notification on `approval_required` |
| **4096-char Telegram limit** | Long answers may fail to send | Shorten prompts; or implement message splitting |
| **Docker `./data` vs `~/.kinthic`** | Broken persistence in containers | Fix compose volumes or document WSL-only install |
| **TUI + Telegram same DB** | SQLite races / corruption | Run one writer process only |
| **`TELEGRAM_PUBLIC_MODE=true`** | Anyone can drive your agent | Never enable; verify in doctor |
| **MCP + terminal + code apply all on** | Large remote execution surface | Keep MCP read-only; approvals on |
| **Pair codes expire in 10 min** | Onboard pairing timeouts confuse users | Regenerate with `kinthic telegram pair` |
| **Approval timeout 120s** | Slow operators lose the turn | `/approvals` quickly; or increase timeout / add push |
| **Background notifications poll every 60s** | Delayed goal-complete messages | Acceptable for v1; not used for tool approvals today |
| **`.env.example` still uses `ARIA_*` names** | Confusing for new users | Align env names in docs before launch |

### Approval flow (current behavior)

When a high-risk tool runs on Telegram:

1. Tool registry queues approval in SQLite (`tool_approvals`).
2. Cognitive loop waits up to **120 seconds**, polling for approve/reject.
3. Operator must run **`/approvals`** then **`/approve <id>`** — there is **no automatic Telegram message** when approval is created (unlike background-goal notifications, which use the `notifications` table + 60s poll).

Reference: `silex/tools/registry.py` → `execute_with_gate()`, `silex/adapters/telegram.py` → `_approvals_command`.

### Security model summary

```
Inbound message
  → telegram_user_allowed()?  (pair / allowlist / NOT public mode)
  → CognitiveLoop.process()
  → Tool call?
      → Ethics engine
      → Approval gate (if required)
      → Execute or refuse
  → Reply (Markdown with plain-text fallback)
```

Pairing storage: `~/.kinthic/config/` settings via `RuntimeSettingsStore` (`paired_users`, `pair_codes` with TTL).

---

## Suggested fix order before announcement

If time is limited, prioritize:

1. **P0 security** — public mode off, pairing works, unpaired denied
2. **P0 approval UX** — document `/approvals` in quickstart **or** ship approval push to Telegram
3. **P0 golden path** — fresh VM install → onboard → telegram run
4. **P1 message splitting** — avoid silent failures on long replies
5. **P1 Docker** — fix or remove from docs
6. **P2 MCP / skills polish**

---

## Quick reference commands

```bash
# Install & configure
curl -fsSL https://kinthic.openyf.dev/install.sh | bash
kinthic onboard
kinthic doctor --ping

# Telegram
kinthic telegram pair          # generate PAIR- code
kinthic telegram run           # start bot

# Operator
kinthic doctor                 # security + MCP status
kinthic skills list
kinthic mcp list
```

In Telegram (paired user): `/status` · `/skills` · `/approvals` · `/approve <id>` · `/logout`

---

## Sign-off

| Area | Owner | Date | Pass? |
|------|-------|------|-------|
| Fresh install golden path | | | |
| Telegram pairing & deny default | | | |
| Tool safety defaults | | | |
| Approval workflow | | | |
| 30-min drill | | | |
| Hosted install.sh + catalog | | | |
| Docs (README, quickstart, WSL) | | | |

**Launch approved when all P0 items pass and P1 gaps are either fixed or explicitly documented.**
