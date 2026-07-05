import asyncio
from silex.tools.web_extract import WebExtractTool


async def main():
    import unittest.mock

    mock_llm = unittest.mock.AsyncMock()
    mock_cog = unittest.mock.MagicMock()
    mock_cog.response = "MOCK COMPRESSED LLM SUMMARY"
    mock_llm.think.return_value = mock_cog

    tool = WebExtractTool(llm=mock_llm)

    print("[TEST] Fetching a normal page (< 5k chars)...")
    res = await tool.execute(url="https://example.com")
    print(f"Result length: {len(res)}\nSnippet: {res[:100]}\n")

    # We can't easily mock httpx inside the tool from the outside without patch,
    # so we'll test the raw parsing by overriding char_count.
    # Actually example.com is very small, so it returns raw.

    print("[TEST] Done.")


if __name__ == "__main__":
    asyncio.run(main())
