# Kinthic CLI Reference

Kinthic is completely controllable via the `kinthic` command line interface. Full docs: [docs.kinthic.com/reference/cli](https://docs.kinthic.com/reference/cli).

## Core & Setup
*   `kinthic init` - First-run wizard. Configures LLM provider, core skills, Telegram pairing, and MCP presets.
*   `kinthic onboard` / `kinthic setup` - Aliases for `init`.
*   `kinthic doctor [--ping]` - Show local setup and security status. The `--ping` flag runs a live API call to verify your configured provider credentials.
*   `kinthic models` - List all supported AI providers and their respective models.
*   `kinthic web` - Launch the local Kinthic web dashboard manually.
*   `kinthic usage` - View historical API usage and estimated token costs.

## Daemons & Execution
*   `kinthic` - Start the default interactive CLI agent session.
*   `kinthic daemon start` - Start the supervisor in the background.
*   `kinthic daemon stop` - Stop the background supervisor.
*   `kinthic daemon status` - Check if the daemon is running.
*   `kinthic daemon logs` - Tail daemon logs.
*   `kinthic daemon run` - Run the supervisor in the foreground.
*   `kinthic daemon install [--force]` - Install as systemd/LaunchAgent service (survives reboot).
*   `kinthic daemon uninstall` - Remove the installed service unit.

## Integrations (Telegram & Discord)
*   `kinthic channels telegram run` - Run the Telegram bot worker.
*   `kinthic channels telegram pair` - Generate a Telegram pairing code.
*   `kinthic channels discord run` - Run the Discord bot worker.

## Skills Management
*   `kinthic skills list` - List catalog and loaded skills (trust, trigger, source).
*   `kinthic skills search <query>` - Search the skill catalog.
*   `kinthic skills install <name or url>` - Install a skill from the catalog or directly from a URL.
*   `kinthic skills uninstall <name>` - Remove an installed skill.
*   `kinthic skills show <name>` - Print full skill markdown body.
*   `kinthic skills refresh` - Merge remote KinthicHub catalog entries.
*   `kinthic skills reload` - Force the engine to reload all skills from disk.

## MCP (Model Context Protocol)
*   `kinthic mcp list` - List all configured MCP servers.
*   `kinthic mcp add <name> [--preset] [--exec] [--args]` - Add a new MCP server.
*   `kinthic mcp enable <name>` - Enable an existing MCP server.
*   `kinthic mcp disable <name>` - Disable an MCP server without deleting it.
*   `kinthic mcp test <name>` - Test connectivity and handshake with an MCP server.
*   `kinthic mcp tools [--server]` - List all tools exposed by connected MCP servers.
*   `kinthic mcp serve [--stdio]` - Run the Silex memory MCP server.
*   `kinthic mcp print-config [--client]` - Print paste-ready MCP client JSON.

## Self-Improvement & Proposals
*   `kinthic proposals list` - List all pending self-improvement proposals.
*   `kinthic proposals approve <id>` - Approve a proposal by its ID prefix.
*   `kinthic proposals reject <id>` - Reject a proposal.

## Maintenance & Data
*   `kinthic data export [--format] [--output] [--success-only] [--since] [--until] [--max]` - Export trajectories (SFT, GRPO, CSV).
*   `kinthic data backup [--output]` - Export entire `~/.kinthic` to zip. Excludes `secrets.json`.
*   `kinthic data restore <archive> [--dry-run | --apply]` - Restore from backup zip.
*   `kinthic data migrate --from <hermes|openclaw> [--path] [--scan-only | --dry-run | --apply]` - Import legacy agent state.

## Benchmarks

*   `kinthic benchmark recall [--seed 42] [--noise 500] [--conditions aged_21d …] [--track retrieval|mcp] [--output path.json] [--report path.md]` - Run the **memory recall** needle-in-haystack benchmark (Silex hybrid retrieval vs keyword / vector / no-memory baselines). Writes `benchmarks/memory_recall/results/REPORT.md` by default.
*   `:benchmark` / `/benchmark` (inside the TUI) - **Different test**: LLM reasoning quality on fixed science/philosophy questions, not memory retrieval.

Full methodology and published numbers: [benchmarks/memory-recall.md](benchmarks/memory-recall.md).
