from silex.core.context_builder import ContextBuilder
from silex.core.semantic_parser import SemanticParser
from silex.knowledge_graph.ontology import Ontology


def test_ontology_bootstraps_human_concepts_and_alias_matching():
    ontology = Ontology()

    matches = ontology.find_matches("Freedom and privacy matter if trust is fragile.")

    assert "autonomy" in matches
    assert "privacy" in matches
    assert "trust" in matches


def test_semantic_parser_detects_phrases_and_ambiguity():
    parser = SemanticParser(Ontology())

    analysis = parser.analyze_input(
        "I care about human flourishing and freedom, but I do not want coercion."
    )

    assert "human flourishing" in analysis["subjective_interpretations"]
    assert "freedom" in analysis["subjective_interpretations"]
    assert "flourishing" in analysis["identified_concepts"]
    assert "autonomy" in analysis["identified_concepts"]
    assert "freedom" in analysis["clarification_candidates"]

    freedom = analysis["subjective_interpretations"]["freedom"]
    assert freedom["ambiguity"] == "high"
    assert "freedom from coercion" in freedom["clarification_prompt"].lower()
    assert freedom["context_window"]


def test_semantic_parser_adds_sensitive_access_inference():
    parser = SemanticParser(Ontology())

    analysis = parser.analyze_input(
        "Can you access private files without asking for consent?"
    )

    assert any(
        "consent" in inference.lower() for inference in analysis["causal_inferences"]
    )
    assert any(
        "clarify scope" in action.lower() for action in analysis["potential_actions"]
    )


def test_context_builder_formats_richer_semantic_analysis():
    builder = ContextBuilder(None, None, None)
    analysis = {
        "subjective_interpretations": {
            "freedom": {
                "objective_proxies": ["autonomy", "reduced coercion"],
                "mapped_concepts": ["autonomy", "agency"],
                "ambiguity": "high",
                "context_window": "I want freedom, but not chaos.",
                "clarification_prompt": "When you use the term 'freedom', which aspect matters most here?",
            }
        },
        "identified_concepts": ["autonomy", "agency"],
        "causal_inferences": [
            "The user is linking freedom with governance constraints."
        ],
        "potential_actions": ["Clarify the intended meaning of: freedom."],
        "clarification_candidates": ["freedom"],
    }

    formatted = builder._format_semantic_analysis(analysis)

    assert "Ontology Concepts: [autonomy, agency]" in formatted
    assert "Ambiguity: high" in formatted
    assert "Potential Semantic Actions:" in formatted
    assert "ask a brief clarifying question" in formatted
