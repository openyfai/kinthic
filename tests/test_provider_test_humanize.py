"""Unit tests for provider connectivity error mapping."""

from silex.llm.provider_test import humanize_llm_error


def test_humanize_invalid_key() -> None:
    msg, hint, code = humanize_llm_error(
        Exception("Error 401: Incorrect API key provided"), "openai"
    )
    assert code == "invalid_api_key"
    assert "dashboard" in hint.lower() or "key" in hint.lower()


def test_humanize_rate_limit() -> None:
    msg, hint, code = humanize_llm_error(
        Exception("429 Too Many Requests"), "openrouter"
    )
    assert code == "rate_limited"


def test_humanize_ollama_refused() -> None:
    msg, hint, code = humanize_llm_error(Exception("Connection refused"), "ollama")
    assert code == "ollama_unreachable"
