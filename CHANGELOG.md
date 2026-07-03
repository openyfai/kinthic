# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-02
### Added
- **Migration Tool**: `kronos migrate scan` and `kronos migrate import` for seamless transition from Hermes and OpenClaw.
- **Secure Skill Growth**: Agents can now autonomously write and patch their own `.md` skills using the `skill_manage` tool, gated securely behind Telegram `/approve`.
- **KronosHub Registry**: Expanded built-in catalog to 15 curated workflows, with new tests and installation endpoints.
- **Community Scaffolding**: Added `#setup-help`, `#skills`, `#security`, and `#showcase` Discord channels, Issue templates, and 20 pinned Good First Issues.
- **Rate Limiting**: Telegram `/pair` requests are now strictly rate-limited for unauthenticated users.

### Security
- **Doctor Warnings**: `kronos doctor` now proactively alerts if Telegram public mode is enabled alongside terminal access or auto-approvals.
- **Strict Sandbox Mode**: Verified plugin signatures and enforced `KRONOS_MEMORY_GUARD_STRICT`.
