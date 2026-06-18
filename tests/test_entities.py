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


from backend import entities


def test_norm_collapses_whitespace():
    assert entities._norm("  할머니   캐릭터 ") == "할머니 캐릭터"
    assert entities._norm(None) == ""


def test_gather_occurrences_orders_and_filters():
    scenes = [
        {"sceneNumber": 1, "characters": ["할머니", ""], "location": "거실", "props": ["포스트잇"]},
        {"sceneNumber": 2, "characters": [], "location": "", "props": []},
    ]
    occ = entities._gather_occurrences(scenes)
    assert occ == [
        {"type": "character", "raw": "할머니", "scene": 1},
        {"type": "location", "raw": "거실", "scene": 1},
        {"type": "prop", "raw": "포스트잇", "scene": 1},
    ]


def test_fallback_entities_dedupes_by_norm():
    occ = [
        {"type": "character", "raw": "할머니", "scene": 1},
        {"type": "character", "raw": "할머니", "scene": 2},
        {"type": "location", "raw": "거실", "scene": 1},
    ]
    ents = entities._fallback_entities(occ)
    assert len(ents) == 2
    grandma = next(e for e in ents if e["type"] == "character")
    assert grandma["id"] == "character-1"
    assert grandma["scenes"] == [1, 2]
    assert grandma["first_scene"] == 1
    assert grandma["aliases"] == ["할머니"]


def test_backlink_scenes_maps_ids_via_aliases():
    scenes = [
        {"sceneNumber": 1, "characters": ["할머니"], "location": "거실", "props": []},
        {"sceneNumber": 2, "characters": ["할머니 캐릭터"], "location": "", "props": []},
    ]
    ents = [
        {"id": "char-grandma", "type": "character", "name": "할머니",
         "aliases": ["할머니", "할머니 캐릭터"]},
        {"id": "loc-living", "type": "location", "name": "거실", "aliases": ["거실"]},
    ]
    updated = entities._backlink_scenes(scenes, ents)
    assert updated == 2
    assert scenes[0]["character_ids"] == ["char-grandma"]
    assert scenes[0]["location_id"] == "loc-living"
    assert scenes[0]["prop_ids"] == []
    assert scenes[1]["character_ids"] == ["char-grandma"]
    assert scenes[1]["location_id"] == ""


def test_backlink_unmatched_logs_and_skips():
    scenes = [{"sceneNumber": 1, "characters": ["미지의인물"], "location": "", "props": []}]
    events = []
    updated = entities._backlink_scenes(scenes, [], on_event=events.append)
    assert updated == 0
    assert scenes[0]["character_ids"] == []
    assert any("미매칭" in e for e in events)
