# Changelog

All notable changes to ARIA are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions use [Semantic Versioning](https://semver.org/).

---

## [1.2.1] - 2026-05-18

### Fixed

- **Centralized runtime path to `~/.vyn/`** — All data (database, vector store, secrets, logs, workspace) now lives under `~/.vyn/` instead of being scattered across the project directory and Python site-packages. Includes idempotent migration from legacy `data/` on first run.
- **`vyn stop` was completely broken** — The stop command pointed at the non-existent `data/aria.pid` file. It now reads `~/.vyn/daemon.lock`, which the daemon writes on startup.
- **File reader sandbox bypass** — `file_reader.py` was reading `ARIA_WORKSPACE` directly from the environment at module level, ignoring `config.py`. It now uses the centralized `WORKSPACE_DIR` constant.
- **Code editor sandbox bypass** — `code_editor.py` fell back to `Path.cwd()` (the repo root) when `ARIA_WORKSPACE` was unset, allowing writes anywhere in the repository. Fixed to use `WORKSPACE_DIR` from config.
- **`_saved_security_flag()` NoneType crash** — The function referenced `_settings_store` directly before the lazy store was initialized, causing `AttributeError: 'NoneType' object has no attribute 'load_settings'`. Fixed to use `get_settings_store()`.
- **Lint errors breaking CI** — Fixed 7 ruff errors: 5 unused imports (F401), 1 undefined `VYN_HOME` (F821), 1 undefined `RuntimeSettingsStore` forward reference (F821). CI (`ruff check .`) now passes clean.
- **Daemon log rotation** — `~/.vyn/logs/daemon.log` now rotates at 10 MB with 3 historical files retained.
- **Doctor warning text** — Updated stale `data/secrets.json` reference to `~/.vyn/secrets.json`.

## [1.2.0] - 2026-05-18

### Changed

- **Rebranding:** Renamed the primary agent persona from ARIA to VYN. ARIA is now maintained specifically as the underlying Causal Memory Engine powering VYN.
- **World Model Upgrade:** Advanced the causal graph generation and node mapping for improved associative reasoning.
- **Daemon Integration:** Added robust daemonizing features for 24/7 background cognitive processing.

## [1.1.6] - 2026-05-15

### Fixed

- **Robust path resolution for the Web Dashboard.** The `aria web` command now correctly locates the dashboard assets relative to the installed package directory, rather than the current terminal folder. This allows you to launch the dashboard from any directory on your system.

## [1.1.5] - 2026-05-15

### Fixed

- **Universal Provider configuration now overrides .env defaults.** Fixed a priority bug where a pre-filled `ARIA_MODEL=gemini-2.5-flash` in the `.env` file would lock the system to Gemini, even if a user configured a custom provider during setup. Custom provider settings now strictly prioritize user-defined models.

## [1.1.4] - 2026-05-15

### Fixed

- **Custom Base URLs are now correctly verified during setup.** The connectivity tester (`ping_provider`) was previously ignoring the user-provided Base URL and falling back to provider defaults (like Google/Gemini). It now correctly routes the verification request to the specified custom endpoint.

## [1.1.3] - 2026-05-15

### Fixed

- **Universal Provider connectivity bypass.** Removed a restrictive internal catalog check that blocked custom model IDs (e.g., `gpt-5.5`) because they weren't in ARIA's static supported list. Setup now allows any model ID through for custom providers.

## [1.1.2] - 2026-05-15

### Added

- **Required field validation in setup.** To prevent terminal pastes from accidentally skipping steps, "Base URL" and "Model ID" are now required fields in the Universal Provider flow. The wizard will re-prompt until a valid input is received.

## [1.1.1] - 2026-05-15

### Changed

- **"Apple Slab" Minimalist Onboarding.** Refined the terminal setup experience into a high-fidelity, distraction-free UI.
- **Silent Security Diagnostics.** Moved verbose Windows-specific security warnings from the main startup flow to the `aria doctor` command to maintain a clean CLI aesthetic while keeping transparency accessible.

## [1.0.7] - 2026-05-14

### Fixed

- **Windows process lock check now handles Access Denied errors.** On Windows, `os.kill(pid, 0)` could throw `WinError 11` for stale locks instead of correctly signaling a dead process. This crashed ARIA startup. Now treats `WinError 11` as a stale lock trigger for safe recovery.

## [1.0.6] - 2026-05-14

### Fixed

- **Web dashboard is now correctly included in PyPI wheels.** Fixed a packaging issue where the `aria/web_dist` directory was omitted by `setuptools` despite being in `pyproject.toml`. Hardened the build workflow to build the UI and copy it into the package before building the wheel.

### Changed

- **Simplified installation.** Removed the redundant `[full]` extra. All core features (dashboard, providers, core tools) are now part of the base `pip install openyfai-aria` command.

## [1.0.5] - 2026-05-10

### Security

- **The code editor can no longer bypass the ethics engine.** Previously, when `ARIA_ENABLE_CODE_APPLY=true` was set, the code editor tool skipped the ethics engine and the approval queue entirely — it applied file changes directly to disk with zero human oversight. Now the tool *always* creates a draft proposal. The `code_apply` flag only controls whether the approval queue auto-approves, it does NOT skip the ethics check.
- **The code editor is now sandboxed to your workspace, not the entire project.** The code editor was using the repo root as its boundary — meaning the AI could propose (and in autonomous mode, apply) edits to its own source code, the web server, the database, or any file in the repository. It now uses the same `ARIA_WORKSPACE` boundary as the file reader, keeping writes inside the designated workspace directory.
- **Eliminated all remaining `shell=True` subprocess calls.** The UI build step (`npm install && npm run build`) and the daemon launcher (`nohup ... &`) both used shell=True — the same class of vulnerability that was fixed in `aria stop` in v1.0.4. Both now use list-form arguments with no shell involved. The daemon launcher uses `subprocess.Popen` with `start_new_session=True` instead of `nohup`.
- **WebSocket messages are now size-limited at the transport layer.** Previously, a client could send a multi-gigabyte message through the WebSocket and ARIA would buffer the entire thing into memory. Now `uvicorn` rejects oversized messages before they reach Python. The limit is configurable via `ARIA_WS_MAX_MESSAGE_CHARS` (default: 2MB).

### Fixed

- **Non-Gemini providers no longer crash on transient errors or malformed JSON.** The retry-with-backoff decorator and JSON repair logic were previously Gemini-exclusive. They've been extracted into shared utilities in `base.py` and applied to all providers — OpenAI, Anthropic, OpenRouter, DeepSeek, Mistral, Groq, and Ollama. Users on any provider now get automatic retries on 429/503 errors and graceful handling of markdown-wrapped JSON.
- **Usage tracker no longer loses data on fast API calls.** The usage log ID was generated from a timestamp, so two LLM calls completing in the same millisecond got the same ID and one was silently dropped. Now uses UUID4.
- **Bare exception handler in code editor replaced.** A `except:` that silently swallowed all errors (including KeyboardInterrupt) has been replaced with specific exception types.
- **ARIA no longer forgets most of what you said.** The history sanitizer was capping user messages at 200 characters before embedding them in conversation context. If you sent a 1000-character message, ARIA only remembered the first 200 characters in future turns. Increased to 2000 characters — the prompt budget (120K chars) already provides the macro-level cap.
- **Background agent can no longer burn unlimited API tokens on goal loops.** The proactive background loop could create goals, complete them, and repeat — each cycle burning API tokens. Now enforces a 10-minute cooldown between goal state transitions (configurable via `ARIA_GOAL_COOLDOWN_SECONDS`). All goal state changes are logged prominently at INFO level.
- **Windows users now get a clear warning about API key file security.** On Windows, `data/secrets.json` has no file permission protection (Windows doesn't support Unix chmod). ARIA now logs a warning recommending environment variables over the secrets file on Windows.

### Changed

- **`PROJECT_ROOT` is now defined once, not five times.** Five files each defined their own `PROJECT_ROOT` by counting parent directories from their own location. If any file moved, it silently broke. Now defined once in `settings.py` and imported everywhere.

### Added

- **New security tests for the code editor sandbox and ethics bypass.** Eight new tests prove: paths outside the workspace are rejected, dotfiles are blocked, path traversal attacks fail, the autonomous apply path no longer exists in the source code, and the registry correctly delegates approval decisions based on the code_apply flag.

## [1.0.4] - 2026-05-10

### Security

- **Fixed a command injection vulnerability in `aria stop`.** The old code read a process ID from a file and passed it directly into a shell command. If that file was ever tampered with, the contents would execute as a real command on your machine. The fix validates the PID as a number and uses Python's `os.kill()` directly — no shell involved.
- **Fixed the file reader sandbox leaking outside your project.** When ARIA was installed via `pip install`, the file reader tool's safe boundary accidentally pointed to Python's `site-packages` folder — meaning the AI could read files from other installed packages. The fix uses a new `ARIA_WORKSPACE` environment variable (defaulting to your current directory) to keep the sandbox tight and predictable.

### Fixed

- **Telegram proactive messages no longer fail silently.** If ARIA tried to send you a proactive Telegram message and it failed (bad token, rate limit, network issue), the error was completely hidden — no log, no warning. Now all failures are logged so you can actually diagnose problems.
- **The Docker sandbox tool no longer freezes the entire app.** When ARIA ran a command inside Docker, it blocked everything — no chat, no WebSocket updates, nothing — for up to 60 seconds while waiting for the container. Now the Docker calls run in a background thread so the rest of ARIA keeps working.

### Added

- **`tests/test_security_fixes.py`**: Four test classes proving each vulnerability is closed — shell injection, sandbox escape, swallowed errors, and async blocking.

---

## [1.0.3] - 2026-05-10

### Fixed

- **ARIA no longer crashes when a previous session didn't shut down cleanly.** If ARIA was killed (power loss, Ctrl+C, crash) and you tried to start it again, it would refuse with a scary "Another ARIA process is already using this data directory" error. Now it checks whether that old process is actually still running. If it's dead, ARIA cleans up the stale lock file and starts normally.
- **Running `aria web` when ARIA is already running now opens your browser** instead of crashing. It detects the existing process and opens `http://127.0.0.1:8000` for you.
- **First-time developers no longer see a blank fallback page.** If you cloned the repo and ran `aria web` without building the UI first, you got a plain HTML page saying the dashboard was missing. Now ARIA detects the situation, runs `npm install && npm run build` automatically, and shows you the progress.

---

## [1.0.2] - 2026-05-10

### Changed

- **Simplified installation.** All dependencies are now included in the base package. The install command is simply `pip install openyfai-aria` — no more `[full]` extra.
- **Simplified README.** Replaced the technical multi-path setup instructions with a clean, three-step quickstart.

### Added

- **GitHub Actions release workflow** (`.github/workflows/release.yml`): Push a version tag and the package is automatically built and published to PyPI.

---


## [1.0.1] - 2026-05-10

### Changed

- **README** and **docs/quickstart**: single Python story (**>=3.11**); **PyPI-first** quick start (`pip install openyfai-aria` then `aria web` / `aria setup`); contributor path for git clone + editable install; Node only for frontend development.
- **PyPI one-line description** in `pyproject.toml` clarified for the project page.

### Added

- **`aria/web_dist/`** for **pre-built dashboard** assets shipped inside wheels (populated in CI, not committed except `__init__.py`).
- **`aria.utils.dashboard_static.resolve_dashboard_dir`**: serves packaged `web_dist/` after `pip install`, or `aria-ui/out/` in a source checkout.
- **`.github/workflows/publish-pypi.yml`**: build `aria-ui`, copy export into `aria/web_dist/`, `python -m build`, publish to PyPI via **Trusted Publishing** (configure in PyPI project settings).

### Notes

- Configure **Trusted Publishing** on [pypi.org](https://pypi.org) for repository `openyfai/aria` and workflow **`publish-pypi.yml`** (optional: match a GitHub **Environment** like `pypi` on both GitHub and PyPI for approval gates). Alternative: **`PYPI_API_TOKEN`** secret and the `with: user/password` block in the workflow file.

---

## [1.0.0] - 2026-05-08

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
- `docs/planning/ROADMAP.md`: Phased public roadmap.
- `CODE_OF_CONDUCT.md`: Community standards.
- `docs/assets/`: Included real screenshots and GIFs (onboarding, chat/monologue, graph, operator/usage) for the README.
- `docs/demo-script.md`: 30-second launch demo recording script.
- `docs/planning/launch-checklist.md`: Pre-public-release gate checklist.
- `docs/planning/launch-issue-backlog.md`: 20 seeded beginner-friendly issues for launch day.

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

[Unreleased]: https://github.com/openyfai/aria/compare/v1.0.4...HEAD
[1.0.4]: https://github.com/openyfai/aria/compare/v1.0.3...v1.0.4
[1.0.3]: https://github.com/openyfai/aria/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/openyfai/aria/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/openyfai/aria/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/openyfai/aria/releases/tag/v1.0.0
