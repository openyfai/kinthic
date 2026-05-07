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
pip install -e ".[full,dev]"
cd aria-ui
npm install
cd ..
```

Run checks:

```bash
pytest
cd aria-ui && npm run lint && npm run build
```

## Clean-Room Install Checklist

Use this before merging onboarding, packaging, or release changes:

1. Start from a fresh checkout on Python `3.12+`.
2. Run `pip install -e ".[full,dev]"`.
3. Confirm `aria models`, `aria doctor`, `aria setup`, and `aria web` work.
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
