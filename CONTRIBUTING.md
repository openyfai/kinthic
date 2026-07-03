# Contributing To Silex

Thanks for helping improve Silex.

## Good First Contributions

- Add or refine Markdown skills in `skills/`
- Improve onboarding copy and docs
- Add provider adapters or model metadata
- Harden security defaults and audits
- Improve operator, usage, or graph UI

## Local Setup

```bash
pip install -e ".[dev]"
cd kronos-ink-ui
npm install
cd ..
```

Run checks:

```bash
pytest
cd kronos-ink-ui && npm run build
```

## Release packaging (maintainers)

Kronos distributes precompiled standalone TUI binaries (`kronos-ui-linux-x64`, `kronos-ui-darwin-x64`, `kronos-ui-darwin-arm64`) via GitHub Releases. The Python backend reasoning engine is installed directly from the GitHub repository during the installer execution.

CI builds and uploads these compiled binaries automatically when a new release tag is pushed (see `.github/workflows/release.yml`).

To trigger a release build:
1. Ensure the version string is bumped to the target version (e.g., `1.0.0`) in:
   - [pyproject.toml](file:///E:/AGI/pyproject.toml)
   - [__init__.py](file:///E:/AGI/silex/__init__.py)
   - [package.json](file:///E:/AGI/kronos-ink-ui/package.json)
2. Create and push a new git tag matching the version prefix:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. The GitHub release workflow will compile the TUI binary for all three supported platforms and attach the executable binaries directly to the GitHub release.

## Clean-Room Install Checklist

Use this before merging onboarding, packaging, or release changes:

1. Start from a fresh checkout on Python `3.11+`.
2. Run `pip install -e ".[dev]"`.
3. Confirm `kronos models`, `kronos doctor`, `kronos setup`, and `kronos web` work.
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
