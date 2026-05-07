# Changelog

All notable changes to ARIA are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions use [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Changed

- PyPI/project package name renamed from `aria-agi` to `aria`; optional extras are unchanged (`aria[full]`, `aria[providers]`, etc.).

### Added

**Multi-provider architecture**
- `aria/llm/base.py`: `SupportsLLM` protocol and `BaseLLMProvider` ABC with `complete_json` for structured output.
- `aria/llm/catalog.py`: `MODEL_CATALOG` covering Gemini, OpenAI, Anthropic, OpenRouter, DeepSeek, Mistral, Groq, and Ollama with tier, capability, and cost metadata.
- `aria/llm/factory.py`: `build_provider` factory that reads active settings and constructs the correct provider instance.
- `aria/llm/openai_compat.py`: `OpenAICompatibleProvider` supporting OpenAI, OpenRouter, DeepSeek, Mistral, Groq, and any Ollama-compatible endpoint.
- `aria/llm/anthropic_provider.py`: Native Anthropic provider with JSON-mode prompting.

**Runtime settings and secrets store**
- `aria/runtime/settings.py`: `RuntimeSettingsStore` — local JSON-backed settings and secrets with atomic writes and file-mode hardening on POSIX.
- `aria/runtime/usage.py`: `UsageTracker` for per-provider, per-model request and token tracking with cost estimation.
- `aria/storage/database.py`: `llm_usage` table and `tool_approvals` columns for `expected_outcome` and `execution_result_json`.

**Web server and bootstrap**
- `scripts/web_server.py`: `GET /api/bootstrap` — public endpoint returning auth requirements, setup status, and provider list without credentials.
- WebSocket auth handshake: key sent on open, `auth_ok` received before connection is marked live.
- Rate limiting on all REST and WebSocket paths with per-client bucketing.
- Server-side enforcement of `ARIA_WEB_API_KEY` for any non-loopback bind.

**CLI operator tooling**
- `scripts/cli.py`: `aria setup`, `aria doctor`, `aria models`, `aria web`, `aria telegram pair/run` with interactive prompts.
- `aria doctor` now reports browser actions, terminal execution, code apply, Telegram public mode, remote bind without key, and multi-writer risk as named warnings.
- `scripts/demo.py`: Expanded into a structured walkthrough with scene, prompt, and capture notes.

**Web UI**
- `aria-ui/src/components/SetupWizard.tsx`: First-run setup with provider/model picker, key input, security toggles, and a `Test provider` button wired to `/api/setup/test-provider`.
- `aria-ui/src/components/SettingsView.tsx`: Post-setup settings for provider, model, API keys, autonomy policy, usage budget, and client-side API base override.
- `aria-ui/src/app/page.tsx`: API-key gate shown before protected calls when remote auth is required; starter prompts in empty chat state; setup success banner.
- `aria-ui/src/components/Sidebar.tsx`: `Operator` uses `Shield01Icon`; `Settings` uses `Settings02Icon`.
- `aria-ui/src/components/OperatorPanel.tsx`: Telegram public mode warning when active.
- `aria-ui/src/hooks/useAriaSocket.ts`: `enabled` prop defers socket and session fetch until auth/bootstrap is resolved.
- `aria-ui/src/lib/api.ts`: `clearApiKey`, `setApiBase`, and `getApiKey` helpers for localStorage-backed auth.

**Security**
- `aria/utils/config.py`: Autonomy flags (`terminal_execution`, `code_apply`, `browser_actions`, `background_actions`, `require_tool_approvals`) now fall back to persisted settings before env defaults.
- `telegram_public_mode_enabled()` helper consolidated in config and used by both the Telegram bot and cognitive loop health report.
- Process lock on startup prevents accidental multi-writer scenarios.
- Telegram deny-by-default with short-lived pairing codes.

**Skills ecosystem**
- `skills/README.md`: Skill format spec, contribution rules, and "submit your first skill in 5 minutes" walkthrough.
- `skills/repo_researcher.md`: Flagship demo skill aligned with the launch prompt sequence.
- `.github/ISSUE_TEMPLATE/skill_request.md`: Skill request template for community contribution.

**Documentation and release readiness**
- `README.md`: Rewritten with separate install paths (terminal, web, Docker), requirements, "See the visual brain in 60 seconds" quickstart, safe defaults card, and links to all community docs.
- `aria-ui/README.md`: Node 20 requirement, link to root README.
- `CONTRIBUTING.md`: Clean-room install checklist for onboarding/packaging PRs.
- `SECURITY.md`: Private vulnerability reporting guidance and security contact path.
- `CHANGELOG.md`: This file.
- `ROADMAP.md`: Phased public roadmap.
- `CODE_OF_CONDUCT.md`: Community standards.
- `docs/assets/`: Four placeholder SVG assets (onboarding, chat/monologue, graph, operator/usage) ready to replace with real screenshots before launch.
- `docs/demo-script.md`: 30-second launch demo recording script.
- `docs/launch-checklist.md`: Pre-public-release gate checklist.
- `docs/launch-issue-backlog.md`: 20 seeded beginner-friendly issues for launch day.

**CI and packaging**
- `.github/workflows/ci.yml`: `ruff` lint, optional `mypy`, `pytest`, `python -m build` smoke test, UI lint, UI build, and Docker build.
- `.github/dependabot.yml`: Weekly updates for pip, npm, and GitHub Actions.
- `pyproject.toml`: Authors, keywords, classifiers, `[project.urls]`, `[tool.setuptools.packages.find]`, `[tool.pytest.ini_options]`.
- `build-backend` updated from deprecated `setuptools.backends._legacy:_Backend` to `setuptools.build_meta`.
- `MANIFEST.in`: Excludes `aria-ui/node_modules`, `.next`, `out`, `scratch`, and `workspace` from sdist.
- `scripts/__init__.py`: Package marker so `scripts.*` entrypoints are resolved correctly.

**Tests**
- `tests/test_settings_store.py`: `RuntimeSettingsStore` persistence, pairing, and status.
- `tests/test_tool_approvals.py`: Approval queue, execution on approval, and result storage.
- `tests/test_cli_smoke.py`: `run_models` output, `run_doctor` status, and module importability.

### Changed

- `aria/llm/gemini.py`: Refactored to `BaseLLMProvider`, uses `UsageTracker` and `RuntimeSettingsStore`.
- `aria/llm/router.py`: Provider-agnostic, model IDs from `RuntimeSettingsStore`.
- `aria/core/cognitive_loop.py`: Provider instantiation via `build_provider`; `get_health_status` includes `telegram_public_mode`; new `get_setup_status`, `get_runtime_settings`, `update_runtime_settings`, `get_usage_summary`, `list_supported_providers`, `reload_provider`.
- `aria/core/critic.py`, `debate.py`, `meta_reasoning.py`, `benchmark.py`, `generalization.py`, `memory/pruner.py`: All use `SupportsLLM` instead of direct Gemini calls.
- `aria/tools/registry.py`: `resolve_approval` now executes the approved tool and stores the result.
- `aria/utils/config.py`: Autonomy flags read persisted settings before env defaults; `telegram_public_mode_enabled()` added.
- `docker-compose.yml`: `web` and `telegram` profiles; `ARIA_WEB_HOST=0.0.0.0` set for web; `skills/` volume mounted.
- `.env.example`: Expanded with multi-provider keys, web API key guidance, and autonomy policy flags.
- `scratch/test_browser.py`: Renamed function to `manual_browser_smoke`, added module docstring, excluded from pytest collection.

### Notes on upgrading

- Run `aria setup` or use the web onboarding flow on first run after pulling this version.
- If you were using `GEMINI_API_KEY` directly, it still works as an env-var fallback.
- Docker deployments now require `ARIA_WEB_API_KEY` when binding to `0.0.0.0`.
- The web UI shows an API-key gate on first load if the server is protected.

---

[Unreleased]: https://github.com/0xopenYF/aria/compare/v1.0.0...HEAD
