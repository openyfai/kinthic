from aria.core.identity import KERNEL_PROMPT, build_identity_section


def test_identity_prompt_replaces_no_guardrails_language():
    assert "NO GUARDRAILS" not in KERNEL_PROMPT
    assert "Respect consent, privacy, and user autonomy." in KERNEL_PROMPT
    assert "Remain corrigible" in KERNEL_PROMPT
    assert "Do not pursue domination, coercion, deception, or unsafe escalation." in KERNEL_PROMPT


def test_build_identity_section_merges_persona():
    settings = {
        "identity": {
            "assistant_name": "GLaDOS",
            "persona": "We do what we must because we can."
        }
    }
    prompt = build_identity_section(settings)
    assert "You are GLaDOS." in prompt
    assert "We do what we must because we can." in prompt
    assert "Respect consent, privacy, and user autonomy." in prompt


def test_build_identity_section_empty_persona():
    prompt = build_identity_section({})
    assert "You are ARIA." in prompt
    assert "Use a helpful, precise tone" in prompt

