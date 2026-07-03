"""
Unit tests for the multi-provider WebSearchTool and fallbacks.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from silex.tools.search import WebSearchTool
from silex.utils.config import get_search_secret
from silex.storage.database import Database


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Automatically strip host environment keys to prevent test leakage."""
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)


class MockHttpResponse:
    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


def test_get_search_secret(tmp_path):
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    
    # Setup mocks for Database/secrets
    from silex.runtime.settings import RuntimeSettingsStore
    store = RuntimeSettingsStore(settings_path=tmp_path / "settings.json", secrets_path=tmp_path / "secrets.json")
    
    # 1. No keys set anywhere
    assert get_search_secret("tavily", settings_store=store) == ""
    assert get_search_secret("brave", settings_store=store) == ""
    
    # 2. Set key in store
    store.set_provider_secret("tavily", "tavily-secret-key")
    assert get_search_secret("tavily", settings_store=store) == "tavily-secret-key"
    
    # 3. Env fallback
    with patch("os.getenv", return_value="brave-env-key"):
        assert get_search_secret("brave", settings_store=store) == "brave-env-key"


@pytest.mark.asyncio
async def test_tavily_search_success():
    tool = WebSearchTool()
    
    mock_response = MockHttpResponse(200, {
        "results": [
            {"title": "Tavily Title", "url": "https://tavily.com", "content": "Tavily content snippet"}
        ]
    })
    
    with patch("silex.tools.search.get_search_secret", return_value="mock-tavily-key"), \
         patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_response)) as mock_post:
        
        result = await tool.execute(query="test query", max_results=3)
        
        assert "Tavily" in result
        assert "Tavily Title" in result
        assert "https://tavily.com" in result
        assert "Tavily content snippet" in result
        
        # Verify it passed the key in POST JSON payload
        called_args, called_kwargs = mock_post.call_args
        assert called_kwargs["json"]["api_key"] == "mock-tavily-key"
        assert called_kwargs["json"]["query"] == "test query"


@pytest.mark.asyncio
async def test_brave_search_success():
    tool = WebSearchTool()
    
    mock_response = MockHttpResponse(200, {
        "web": {
            "results": [
                {"title": "Brave Title", "url": "https://brave.com", "description": "Brave snippet description"}
            ]
        }
    })
    
    # Mock Tavily key to be empty, and Brave key to be present
    def mock_secret_lookup(prov):
        if prov == "brave":
            return "mock-brave-key"
        return ""
        
    with patch("silex.tools.search.get_search_secret", side_effect=mock_secret_lookup), \
         patch("httpx.AsyncClient.get", AsyncMock(return_value=mock_response)) as mock_get:
        
        result = await tool.execute(query="brave query", max_results=2)
        
        assert "Brave" in result
        assert "Brave Title" in result
        assert "https://brave.com" in result
        assert "Brave snippet description" in result
        
        # Verify it passed headers and parameters correctly
        called_args, called_kwargs = mock_get.call_args
        assert called_kwargs["headers"]["X-Subscription-Token"] == "mock-brave-key"
        assert called_kwargs["params"]["q"] == "brave query"


@pytest.mark.asyncio
async def test_duckduckgo_fallback_when_apis_fail():
    tool = WebSearchTool()
    
    # Mock no API keys configured
    with patch("silex.tools.search.get_search_secret", return_value=""), \
         patch("silex.tools.search.DDGS") as mock_ddgs:
        
        mock_instance = MagicMock()
        mock_instance.text.return_value = [
            {"title": "DDG Title", "href": "https://ddg.gg", "body": "DDG body snippet"}
        ]
        mock_ddgs.return_value.__enter__.return_value = mock_instance
        
        result = await tool.execute(query="ddg query")
        
        assert "DuckDuckGo" in result
        assert "DDG Title" in result
        assert "https://ddg.gg" in result
        assert "DDG body snippet" in result


@pytest.mark.asyncio
async def test_browser_fallback_when_ddg_fails():
    tool = WebSearchTool()
    
    # Mock DDG failing (throwing exception)
    def mock_ddg_fail(*args, **kwargs):
        raise RuntimeError("DDG Blocked")

    # Mock browser observations
    mock_obs = "BROWSER_OBSERVATION:\n" + json.dumps({
        "result": "Clean scraped google results containing info here. " * 10
    })
    
    with patch("silex.tools.search.get_search_secret", return_value=""), \
         patch("silex.tools.search.DDGS", side_effect=mock_ddg_fail), \
         patch("silex.tools.search.browser_actions_enabled", return_value=True), \
         patch("silex.tools.browser.BrowserTool") as mock_browser_cls:
        
        mock_browser = MagicMock()
        mock_browser.execute = AsyncMock(side_effect=[
            "Successfully navigated",  # navigate action response
            mock_obs                  # scrape action response
        ])
        mock_browser.close = AsyncMock()
        mock_browser_cls.return_value = mock_browser
        
        result = await tool.execute(query="browser search")
        
        assert "Browser Scraper" in result
        assert "Clean scraped google results" in result
        
        # Verify navigation to ddg html URL happened
        mock_browser.execute.assert_any_call(action="navigate", url="https://html.duckduckgo.com/html/?q=browser search")
        mock_browser.execute.assert_any_call(action="scrape")
        mock_browser.close.assert_called_once()
