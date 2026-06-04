import json
from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "skills/scene-decompose/scenes.schema.json"


def test_schema_is_valid_json_and_requires_scenes():
    s = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert s["type"] == "object"
    assert "scenes" in s["properties"]
    assert "narration" in s["properties"]["scenes"]["items"]["required"]


def test_sample_doc_validates():
    s = json.loads(SCHEMA.read_text(encoding="utf-8"))
    doc = {
        "version": "adobe-0.1", "project_id": "demo01", "topic": "t",
        "total_scenes": 1,
        "scenes": [{"sceneNumber": 1, "title": "도입",
                    "narration": "카지노가 세 번 무너졌습니다."}],
    }
    for k in s["required"]:
        assert k in doc
    sc = doc["scenes"][0]
    for k in s["properties"]["scenes"]["items"]["required"]:
        assert k in sc
