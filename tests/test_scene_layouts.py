import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "skills/scene-decompose/scenes.schema.json"
TOKENS = ROOT / "data/artstyle/ae_tokens.json"

LAYOUTS = ["cinematic", "headline_only", "items_list", "metric_spotlight", "bar", "quote"]
NEW_FIELDS = ["layout", "headline", "sub", "items", "value", "label", "chart", "quote_text", "quote_who"]


def test_schema_layout_enum():
    s = json.loads(SCHEMA.read_text(encoding="utf-8"))
    item = s["properties"]["scenes"]["items"]
    enum = item["properties"]["layout"]["enum"]
    for l in LAYOUTS:
        assert l in enum
    assert None in enum  # nullable


def test_schema_new_fields_required_and_nullable():
    s = json.loads(SCHEMA.read_text(encoding="utf-8"))
    item = s["properties"]["scenes"]["items"]
    for f in NEW_FIELDS:
        assert f in item["properties"], f
        assert f in item["required"], f
    # codex strict: 모든 속성이 required에
    assert set(item["required"]) == set(item["properties"].keys())
    # nullable 타입
    assert item["properties"]["headline"]["type"] == ["string", "null"]
    assert item["properties"]["items"]["type"] == ["array", "null"]
    ch = item["properties"]["chart"]
    assert ch["type"] == ["object", "null"]
    assert ch["additionalProperties"] is False
    assert set(ch["required"]) == {"labels", "values", "unit"}


def test_ae_tokens_keys():
    t = json.loads(TOKENS.read_text(encoding="utf-8"))
    assert t["colors"]["accent"] == "#4A90D9"
    for k in ("bgRgb", "textRgb", "mutedRgb", "accentRgb"):
        assert len(t["colors"][k]) == 3
    for k in ("headline", "body", "number", "fallback"):
        assert t["fonts"][k]
    for k in ("headline", "sub", "item", "metric", "metricLabel", "quote", "quoteWho", "barLabel", "barValue"):
        assert isinstance(t["type"][k], (int, float))


def test_skill_md_has_layout_guidance():
    md = (ROOT / "skills/scene-decompose/SKILL.md").read_text(encoding="utf-8")
    assert "레이아웃 선택" in md
    for l in LAYOUTS:
        assert l in md
