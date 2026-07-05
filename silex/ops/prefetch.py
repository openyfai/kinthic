"""One-time prefetch helpers for first-run setup."""

from __future__ import annotations

import importlib.util


def prefetch_embedding_model() -> str | None:
    """Download/warm the Chroma default embedding model if vector extra is installed.

    Returns a user-facing status message, or None if skipped.
    """
    if importlib.util.find_spec("chromadb") is None:
        return "Skipped (install kinthic[vector] for semantic memory)."

    try:
        from chromadb.utils import embedding_functions

        # Constructing DefaultEmbeddingFunction triggers the one-time ONNX download.
        embedding_functions.DefaultEmbeddingFunction()
        return "Embedding model ready (~80MB one-time download complete)."
    except Exception as exc:
        return f"Embedding prefetch skipped: {exc}"
