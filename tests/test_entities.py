import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_entities_schema_valid():
    schema = json.loads((_ROOT / "backend/schemas/entities.schema.json").read_text(encoding="utf-8"))
    items = schema["properties"]["entities"]["items"]
    assert items["properties"]["type"]["enum"] == ["character", "location", "prop"]
    assert items["required"] == ["id", "type", "name"]


def test_entity_registry_skill_exists():
    md = (_ROOT / "skills/entity-registry/SKILL.md").read_text(encoding="utf-8")
    assert "entity-registry" in md
