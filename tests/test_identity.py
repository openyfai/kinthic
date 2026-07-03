from silex.core.identity import KERNEL_PROMPT, build_identity_section


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
    assert "You are Kinthic." in prompt
    assert "Use a helpful, precise tone" in prompt


def test_dynamic_persona_matrix_compilation():
    """Verify that ContextBuilder dynamically compiles identity prompts from persona.yaml."""
    from silex.core.context_builder import ContextBuilder
    from unittest.mock import patch

    # Define a custom temporary persona dictionary
    test_persona = {
        "agent_name": "TuringBot",
        "engine_name": "NUCLEUS",
        "primary_brand": "Turing Core (v1)",
        "personality_archetype": "Autonomous Theoretical Logic Machine",
        "tone_modifiers": [
            "Extremely analytical and precise.",
            "Uses mathematical notation for proofs."
        ],
        "custom_greeting": "TuringBot online. Ready to prove hypotheses."
    }

    # Patch load_persona_config to return our custom persona
    with patch("silex.utils.config.load_persona_config", return_value=test_persona):
        # Create a mock ContextBuilder and invoke _build_identity_section
        builder = ContextBuilder(
            memory_store=None,
            goal_tracker=None,
            session_manager=None
        )
        
        prompt = builder._build_identity_section()
        
        # Verify dynamic substitution occurred correctly
        assert "You are TuringBot." in prompt
        assert "Your cognition is powered by NUCLEUS" in prompt
        assert "NUCLEUS maintains your knowledge graph" in prompt
        assert "Act as the Autonomous Theoretical Logic Machine" in prompt
        assert "Extremely analytical and precise." in prompt
        assert "Uses mathematical notation for proofs." in prompt
        assert "WORKSPACE PROTOCOL:" in prompt


