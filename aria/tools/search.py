"""
Web Search Tool using DuckDuckGo.
"""

from __future__ import annotations

import logging
from ddgs import DDGS
from aria.tools.base import BaseTool

log = logging.getLogger("aria.tools.search")

class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Searches the live internet for current facts, news, or general knowledge."
    schema = {
        "query": "string (the exact search query to execute)",
        "max_results": "integer (optional, default 3, max 5)"
    }

    async def execute(self, **kwargs) -> str:
        query = kwargs.get("query")
        if not query:
            return "Error: 'query' argument is required."
            
        max_results = int(kwargs.get("max_results", 3))
        log.info(f"Executing web_search for: '{query}'")

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                
            if not results:
                return f"No results found for query: '{query}'"
                
            formatted = f"Search Results for '{query}':\n\n"
            for i, r in enumerate(results, 1):
                formatted += f"[{i}] {r.get('title', 'No Title')}\n"
                formatted += f"URL: {r.get('href', 'No URL')}\n"
                formatted += f"Snippet: {r.get('body', 'No Snippet')}\n\n"
                
            return formatted.strip()

        except Exception as e:
            log.error(f"Web search failed: {e}")
            return f"Error executing search: {str(e)}"
