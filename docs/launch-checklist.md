# Launch Checklist

This checklist is the pre-public-release gate for ARIA packaging.

## Product gates

- [x] Fresh local install path documented for Python `>=3.12`.
- [x] `pip install -e ".[full,dev]"` path documented.
- [x] `aria setup` and `aria web` are part of the primary quickstart.
- [x] Docker web path documents `.env`, `ARIA_WEB_HOST=0.0.0.0`, and `ARIA_WEB_API_KEY`.
- [x] Web bootstrap includes an API key gate before protected setup calls.
- [x] One flagship demo prompt is documented and wired into the empty chat state.

## Trust gates

- [x] README communicates safe defaults clearly.
- [x] Security docs are linked from the README.
- [x] Contribution docs are linked from the README.
- [x] `aria doctor` warns about risky settings.
- [x] Telegram public mode is visibly flagged in operator-facing surfaces.

## Release gates

- [x] `python -m pytest tests` is in CI.
- [x] UI lint and build are in CI.
- [x] `python -m build` smoke test is in CI.
- [x] Docker build is in CI.
- [x] Dependabot is configured.

## Before public announcement

- [ ] Replace placeholder assets in `docs/assets/` with real screenshots or GIFs.
- [ ] Record the 30-second launch demo using `docs/demo-script.md`.
- [ ] Create and publish at least 20 beginner-friendly GitHub issues from `docs/launch-issue-backlog.md`.
