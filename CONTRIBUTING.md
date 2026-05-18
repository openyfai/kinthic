# Contributing To ARIA

Thanks for helping improve ARIA.

## Good First Contributions

- Add or refine Markdown skills in `skills/`
- Improve onboarding copy and docs
- Add provider adapters or model metadata
- Harden security defaults and audits
- Improve operator, usage, or graph UI

## Local Setup

```bash
pip install -e ".[dev]"
cd aria-ui
npm install
cd ..
```

Run checks:

```bash
pytest
cd aria-ui && npm run lint && npm run build
```

## PyPI release (maintainers)

Published wheels embed the **built** dashboard under `aria/web_dist/`. CI runs on each **published GitHub Release** (see `.github/workflows/publish-pypi.yml`): ensure **`version` in `pyproject.toml` and `aria/__init__.py`** match the release tag before publishing.

1. Build `aria-ui` (`npm ci` + `npm run build`).
2. Copy `aria-ui/out/*` into `aria/web_dist/` (keeping tracked `__init__.py`).
3. Run `python -m build` and upload with **PyPI Trusted Publishing** (configure the GitHub repo as a trusted publisher for project `openyfai-vyn` in PyPI settings).

**Manual wheel (optional):** after a local `aria-ui` build:

```bash
# bash (Git Bash / WSL / macOS / Linux)
find aria/web_dist -mindepth 1 -maxdepth 1 ! -name '__init__.py' -exec rm -rf {} +
cp -r aria-ui/out/. aria/web_dist/
python -m build
```

On Windows PowerShell, use Explorer or equivalent `robocopy` / manual copy instead of `cp`.

## Clean-Room Install Checklist

Use this before merging onboarding, packaging, or release changes:

1. Start from a fresh checkout on Python `3.11+`.
2. Run `pip install -e ".[dev]"`.
3. Confirm `vyn models`, `vyn doctor`, `vyn setup`, and `vyn web` work.
4. Run the web UI once with a new browser profile or cleared local storage.
5. If Docker behavior changed, verify `docker compose --profile web up --build`.
6. Confirm secrets stay write-only in API responses and UI state.

## Pull Request Guidelines

- Keep PRs focused and reviewable.
- Document behavior changes in the README or relevant docs.
- Prefer safe defaults for anything related to tools, remote access, or secrets.
- Add tests when the change reduces regression risk in a meaningful way.

## Areas We Care About

- Provider/model routing
- Tool approval flow
- Telegram pairing and operator controls
- Usage and audit visibility
- Markdown skills ecosystem

## Commit And Review Style

- Use concise commits that explain why the change exists.
- If a change affects safety, mention the new default and the old risk.
- If a change affects onboarding, test the clean-room install path.
