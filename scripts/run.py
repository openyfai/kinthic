"""
ARIA Entry Point — starts the cognitive loop.

Usage:
    python -m scripts.run
    or
    python scripts/run.py

Phase 2: Added world model commands (:graph, :why, :contradictions, :hypotheses).
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aria.core.cognitive_loop import CognitiveLoop
from aria.ui.terminal import (
    console,
    get_input,
    show_banner,
    show_startup_summary,
    show_error,
    show_warning,
    show_success,
    show_info,
    show_goals,
    show_help,
    show_memories,
    show_search_results,
    show_sessions,
    show_response,
    show_stats,
    # Phase 2
    show_graph_stats,
    show_graph_neighborhood,
    show_causal_chain,
    show_contradictions,
    show_hypotheses,
    # Phase 3
    show_improvements,
    # Phase 4
    show_debate_resolution,
    show_uncertainties,
    # Phase 5
    show_tools,
    # Phase 6
    show_principles,
    # Phase 7
    show_proposals,
    show_benchmark_result,
    show_meta_proposal,
)


async def run() -> None:
    """Main async entry point."""
    loop = CognitiveLoop()

    try:
        # Boot sequence
        show_banner()
        await loop.startup()

        # Show context-aware startup summary
        info = await loop.get_session_info()
        sessions = await loop.get_all_sessions()
        show_startup_summary(
            memory_count=info["total_memories"],
            goal_count=info["active_goals"],
            session_count=len(sessions),
            total_turns=info["total_turns"],
        )

        # Phase 2: Show graph stats at startup if non-empty
        if info.get("graph_nodes", 0) > 0:
            console.print(
                f"  [bright_cyan]◆[/] [dim]World model:[/] "
                f"[bright_cyan]{info['graph_nodes']} nodes[/][dim],[/] "
                f"[bright_cyan]{info['graph_edges']} edges[/]"
            )
            console.print()

        # Main interaction loop
        while True:
            user_input = get_input()

            # Empty input
            if not user_input:
                continue

            # Commands
            if user_input.startswith(":"):
                cmd_parts = user_input.split(maxsplit=1)
                cmd = cmd_parts[0].lower().strip()
                cmd_arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

                if cmd in (":quit", ":exit", ":q"):
                    console.print("\n  [dim]ARIA signing off. Memories persisted.[/]\n")
                    break

                elif cmd in (":help", ":h"):
                    show_help()
                    continue

                elif cmd in (":memories", ":mem"):
                    memories = await loop.get_all_memories()
                    show_memories(memories)
                    continue

                elif cmd in (":goals", ":g"):
                    goals = await loop.get_all_goals()
                    show_goals(goals)
                    continue

                elif cmd in (":stats", ":s"):
                    stats = await loop.get_session_info()
                    show_stats(stats)
                    continue

                elif cmd in (":sessions", ":sess"):
                    sessions = await loop.get_all_sessions()
                    show_sessions(sessions)
                    continue

                elif cmd in (":search",):
                    if not cmd_arg:
                        show_warning("Usage: :search <query>")
                        continue
                    results = await loop.search_memories(cmd_arg)
                    show_search_results(results, cmd_arg)
                    continue

                elif cmd in (":remember", ":rem"):
                    if not cmd_arg:
                        show_warning("Usage: :remember <fact to store>")
                        continue
                    memory = await loop.add_manual_memory(cmd_arg)
                    show_success(f"Stored: \"{memory.content[:50]}\"")
                    continue

                elif cmd in (":forget",):
                    if not cmd_arg:
                        show_warning("Usage: :forget <memory number>")
                        continue
                    try:
                        index = int(cmd_arg)
                        deleted = await loop.forget_memory(index)
                        if deleted:
                            show_success(f"Memory #{index} deleted.")
                        else:
                            show_error(f"Memory #{index} not found.")
                    except ValueError:
                        show_error("Provide a number, e.g. :forget 3")
                    continue

                # Phase 2 — World Model commands

                elif cmd in (":graph",):
                    if cmd_arg:
                        # Show neighborhood of a concept
                        data = await loop.get_graph_neighborhood(cmd_arg)
                        if data:
                            show_graph_neighborhood(data)
                        else:
                            show_warning(
                                f"'{cmd_arg}' not found in the knowledge graph. "
                                f"Talk to ARIA to build the graph."
                            )
                    else:
                        # Show graph stats
                        stats = await loop.get_graph_stats()
                        show_graph_stats(stats)
                    continue

                elif cmd in (":why",):
                    if not cmd_arg or "->" not in cmd_arg:
                        show_warning("Usage: :why <concept A> -> <concept B>")
                        continue
                    parts = cmd_arg.split("->", 1)
                    from_c = parts[0].strip()
                    to_c = parts[1].strip()
                    chain = await loop.get_causal_chain(from_c, to_c)
                    show_causal_chain(chain or [], from_c, to_c)
                    continue

                elif cmd in (":contradictions", ":contra"):
                    contras = await loop.get_contradictions()
                    show_contradictions(contras)
                    continue

                elif cmd in (":hypotheses", ":hypo"):
                    hypos = await loop.get_hypotheses()
                    show_hypotheses(hypos)
                    continue

                elif cmd in (":export",):
                    filepath = await loop.export_session()
                    if filepath:
                        show_success(f"Session exported to: {filepath}")
                    else:
                        show_error("Nothing to export yet.")
                    continue

                elif cmd in (":improvements", ":imp"):
                    improvements = await loop.get_recent_improvements()
                    show_improvements(improvements)
                    continue

                elif cmd in (":debate",):
                    if not cmd_arg:
                        show_warning("Usage: :debate <topic>")
                        continue
                    try:
                        with console.status(
                            "[bright_cyan]  Initializing debate...[/]",
                            spinner="dots",
                            spinner_style="bright_magenta",
                        ) as status:
                            resolution = await loop.run_debate(cmd_arg, status_callback=status.update)
                        show_debate_resolution(resolution)
                    except Exception as e:
                        show_error(str(e))
                        console.print_exception(show_locals=False)
                    continue

                elif cmd in (":uncertainties", ":unc"):
                    uncertainties = await loop.get_uncertainties()
                    show_uncertainties(uncertainties)
                    continue

                elif cmd in (":tools",):
                    show_tools(loop.tool_registry)
                    continue

                elif cmd in (":principles", ":prin"):
                    principles = await loop.get_principles()
                    show_principles(principles)
                    continue

                elif cmd in (":proposals", ":prop"):
                    proposals = await loop.get_proposals()
                    show_proposals(proposals)
                    continue

                elif cmd in (":benchmark", ":bench"):
                    console.print("\n  [bright_magenta]Running benchmark suite (this will take a while)...[/]\n")
                    with console.status(
                        "[bright_magenta]  Benchmarking...",
                        spinner="dots",
                        spinner_style="bright_magenta",
                    ) as status:
                        result = await loop.run_benchmark(status_callback=status.update)
                    show_benchmark_result(result)
                    continue

                elif cmd in (":meta",):
                    console.print("\n  [bright_magenta]Running meta-reasoning analysis...[/]\n")
                    with console.status(
                        "[bright_magenta]  Analyzing performance data...",
                        spinner="dots",
                        spinner_style="bright_magenta",
                    ) as status:
                        proposal = await loop.run_meta_analysis(status_callback=status.update)
                    show_meta_proposal(proposal)
                    continue

                elif cmd in (":clear", ":cls"):
                    console.clear()
                    show_banner()
                    continue

                else:
                    show_error(f"Unknown command: {cmd}. Type :help for options.")
                    continue

            # Cognitive turn — with Rich spinner
            try:
                with console.status(
                    "[bright_cyan]  ARIA is thinking...[/]",
                    spinner="dots",
                    spinner_style="bright_cyan",
                ) as status:
                    response = await loop.process(user_input, status_callback=status.update)
                show_response(response)
            except KeyboardInterrupt:
                console.print("\n  [dim]Thinking cancelled.[/]")
            except Exception as e:
                show_error(str(e))
                console.print_exception(show_locals=False)

    except KeyboardInterrupt:
        console.print("\n\n  [dim]Interrupted. Shutting down...[/]\n")

    finally:
        await loop.shutdown()


def main() -> None:
    """Synchronous wrapper for the async entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
