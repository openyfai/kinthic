import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from aria.llm.base import BaseLLMProvider, CognitiveResponse
from aria.runtime.usage import UsageTracker
from aria.storage.database import Database

class MockProvider(BaseLLMProvider):
    def __init__(self, usage_tracker=None):
        self._usage_tracker = usage_tracker
        super().__init__(default_model="mock-model")
        self.call_count = 0

    def connect(self):
        pass

    async def complete_json(self, *, schema, system_prompt, user_input, images=None, model_override=None, temperature=0.7, request_kind="chat"):
        self.call_count += 1
        return schema(
            reasoning="Mock reasoning step.",
            plan="Mock plan steps.",
            response=f"Mock response {self.call_count}.",
            self_reflection="Mock reflection.",
            confidence=0.9
        )

@pytest.mark.asyncio
async def test_semantic_response_caching(tmp_path):
    db_path = tmp_path / "test_cache.db"
    db = Database(str(db_path))
    await db.connect()

    usage = UsageTracker(db)
    provider = MockProvider(usage_tracker=usage)

    system_prompt = "You are a helpful assistant."
    user_input = "Hello, what is 2+2?"

    # 1. First call: Cache Miss, calls original complete_json
    res1 = await provider.complete_json(
        schema=CognitiveResponse,
        system_prompt=system_prompt,
        user_input=user_input
    )
    assert res1.response == "Mock response 1."
    assert provider.call_count == 1

    # 2. Second call: Cache Hit, retrieves cached response, bypasses API
    res2 = await provider.complete_json(
        schema=CognitiveResponse,
        system_prompt=system_prompt,
        user_input=user_input
    )
    assert res2.response == "Mock response 1."  # Reused from res1
    assert provider.call_count == 1  # call_count remains 1!

    # 3. Third call with different prompt: Cache Miss
    res3 = await provider.complete_json(
        schema=CognitiveResponse,
        system_prompt=system_prompt,
        user_input="Hello, what is 3+3?"
    )
    assert res3.response == "Mock response 2."
    assert provider.call_count == 2

    # 4. Expire the cache (TTL > 900 seconds)
    import hashlib
    hash_input = f"{system_prompt}||{user_input}||{CognitiveResponse.__name__}"
    query_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

    expired_time = (datetime.now(timezone.utc) - timedelta(seconds=901)).isoformat()
    await db.execute(
        "UPDATE response_cache SET created_at = ? WHERE query_hash = ?",
        (expired_time, query_hash)
    )

    # 5. Fourth call: Cache Miss due to expiration
    res4 = await provider.complete_json(
        schema=CognitiveResponse,
        system_prompt=system_prompt,
        user_input=user_input
    )
    assert res4.response == "Mock response 3."
    assert provider.call_count == 3

    await db._conn.close()
