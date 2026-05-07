# ARIA Roadmap

## Launch-Ready MVP — complete

- [x] Multi-provider architecture: Gemini, OpenAI, Anthropic, OpenRouter, DeepSeek, Mistral, Groq, Ollama.
- [x] Provider and model selection from CLI (`aria setup`) and web onboarding without code edits.
- [x] Runtime settings and secrets store backed by local JSON files.
- [x] First-run setup wizard in the web UI with provider key testing.
- [x] Web API key bootstrap gate for remote and Docker deployments.
- [x] Operator panel: approvals, usage monitor, Telegram pairing.
- [x] Tool approval queue with execution on approval and stored result.
- [x] Telegram deny-by-default with short-lived pairing codes.
- [x] `aria doctor` with risky-setting warnings.
- [x] Markdown skills ecosystem with contribution docs and flagship demo skill.
- [x] Accurate install docs for terminal, web, and Docker paths.
- [x] CI: Python tests, ruff, mypy, package build, UI lint/build, Docker build.
- [x] Dependabot for pip, npm, and GitHub Actions.
- [x] CHANGELOG, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, ROADMAP, issue templates.
- [x] Demo script and launch checklist in `docs/`.

---

## V1

The focus is depth over breadth: make the existing surfaces faster, safer, and more auditable before adding new capabilities.

**Provider routing**
- Per-task model routing based on complexity score and token estimate.
- Provider compatibility matrix in docs.
- Fallback chain when a provider call fails.

**Memory and graph**
- Click a graph node and ask "why do you believe this?".
- Source/provenance badges on graph nodes and memories.
- Mark a memory as wrong or stale from the web UI.
- Export and import the knowledge graph.
- "What changed in ARIA's understanding today?" summary command.

**Approval and audit**
- Approval result replay: re-show what happened after a tool was approved.
- Operator audit log export (CSV or JSON) from the web UI.
- Per-tool risk-level documentation.

**Usage and budget**
- Hard cost cap enforcement at provider level.
- Per-session cost breakdown in the operator panel.
- Usage alerts via Telegram when soft cap is approaching.

**Skills**
- Skills loaded without restart (file watcher).
- Skill output preview in the web UI.
- Community skill registry or index.

**Telegram**
- `/skills` command to list active skills.
- Per-user session isolation in multi-user setups.
- Improved approval flow with inline keyboard buttons.

---

## Community Loop

- Replace `docs/assets/` placeholder SVGs with real screenshots and GIFs.
- Record the 30-second launch demo using `docs/demo-script.md`.
- Publish the 20 seeded issues from `docs/launch-issue-backlog.md`.
- Provider adapters contributed by the community.
- External security review of the autonomy and approval surface.
- Benchmark suite expanded with community-contributed test cases.
