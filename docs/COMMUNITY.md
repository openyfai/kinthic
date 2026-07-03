# Welcome to the Kronos Community

Kronos is an AGPL-3.0 licensed open-source autonomous cognitive agent, designed to be run privately on your own hardware or VPS, and securely paired via Telegram. 

## Join the Discord

We use Discord for real-time collaboration, debugging, and sharing skills.
*Invite Link*: [Join the Kronos Discord (Placeholder)](#)

### Channels
- **`#setup-help`**: Stuck on `kronos onboard`? Get help setting up your provider, MCP servers, or pairing your Telegram bot.
- **`#skills`**: Share the custom `.md` workflows you've written, or request a skill to be added to KronosHub.
- **`#security`**: Discuss sandbox hardening, prompt injection defenses, and the `KRONOS_MEMORY_GUARD` architecture.
- **`#showcase`**: Show off the wildest multi-step goals you've successfully completed with Kronos.

## Contributing

We welcome contributions of all sizes! Before opening a PR:
1. Review the [Good First Issues](docs/planning/launch-issue-backlog.md) backlog if you're looking for a place to start.
2. Read the [Plugin Development Guide](PLUGIN_DEVELOPMENT.md) if you are contributing a Skill or Tool.
3. Ensure your PR passes all `pytest` suites.

## Reporting Bugs

Please open a GitHub issue with:
- The output of `kronos doctor`
- The `silex.log` trace
- Steps to reproduce

## Submitting Skills to KronosHub

To submit a new skill to the curated registry, please use the provided [Skill Submission Issue Template](.github/ISSUE_TEMPLATE/skill_submission.md) or open a PR against the `kronos-hub` repository. All submitted skills undergo a strict security audit.
