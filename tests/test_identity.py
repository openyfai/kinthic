from aria.core.identity import IDENTITY_PROMPT


def test_identity_prompt_replaces_no_guardrails_language():
    assert "NO GUARDRAILS" not in IDENTITY_PROMPT
    assert "Respect consent, privacy, and user autonomy." in IDENTITY_PROMPT
    assert "Remain corrigible" in IDENTITY_PROMPT
    assert "Do not pursue domination, coercion, deception, or unsafe escalation." in IDENTITY_PROMPT
