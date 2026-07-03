import json
import tempfile
from pathlib import Path

from silex.knowledge_graph.ontology import Ontology


def test_merge_from_json_file_adds_concept():
    ontology = Ontology()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "overlay.json"
        p.write_text(
            json.dumps({"concepts": {"custom_overlay": {"aliases": ["co"]}}, "relationships": {}}),
            encoding="utf-8",
        )
        ontology.merge_from_json_file(p)

    attrs = ontology.get_concept_attributes("custom_overlay")
    assert "aliases" in attrs
    assert "co" in attrs["aliases"]
