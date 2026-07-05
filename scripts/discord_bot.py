"""Discord bot entry point — delegates to silex.adapters.discord."""

from __future__ import annotations

from silex.adapters.discord import DiscordAdapter


def main() -> None:
    DiscordAdapter().run()


if __name__ == "__main__":
    main()
