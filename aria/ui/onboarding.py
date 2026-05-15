from __future__ import annotations

import os
from typing import Any

from rich.align import Align
from rich.console import Console, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text


class OnboardingUI:
    """
    Minimalist "Apple Slab" UI engine for ARIA onboarding.
    Uses Black & White high-contrast design with centered spatial layouts.
    """

    def __init__(self):
        self.console = Console()
        self._border_style = "bright_black"  # Subtle gray for thin lines
        self._header_style = "bold white"
        self._dim_style = "dim white"

    def clear(self):
        """Clear the terminal screen."""
        self.console.clear()

    def create_slab(
        self,
        title: str,
        content: RenderableType,
        subtitle: str | None = None,
        width: int = 60,
    ) -> Layout:
        """Create a centered panel 'slab' with the given content."""
        # Header text
        header = Text(f"\n{title.upper()}\n", style=self._header_style, justify="center")
        
        # Combine everything into a vertical renderable
        body = []
        body.append(header)
        body.append(content)
        if subtitle:
            body.append(Text(f"\n{subtitle}", style=self._dim_style, justify="center"))
        body.append(Text("\n"))

        # Create the panel (The Slab)
        panel = Panel(
            Align.center(Group(*body)),
            border_style=self._border_style,
            padding=(1, 2),
            width=width,
        )

        # Center vertically and horizontally
        return Align.center(panel, vertical="middle")

    def render_step(self, title: str, content: RenderableType, subtitle: str | None = None):
        """Render a single step of the onboarding."""
        self.clear()
        slab = self.create_slab(title, content, subtitle)
        self.console.print(slab)

    def prompt(self, text: str, default: str = "", password: bool = False) -> str:
        """A minimalist prompt styled to match the slab aesthetic."""
        prompt_text = Text(f"  > {text}: ", style="bold white")
        return self.console.input(prompt_text, password=password).strip() or default


from rich.console import Group
