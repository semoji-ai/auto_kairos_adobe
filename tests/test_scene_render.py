import json
from pathlib import Path
from backend import scene_render


def _mksheet(tmp_path, rel):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"\x89PNG\r\n")


def test_resolve_scene_refs_existing_only(tmp_path):
    _mksheet(tmp_path, "references/characters/char-1.png")
    ents = {
        "char-1": {"id": "char-1", "type": "character", "name": "하루", "sheet": "references/characters/char-1.png"},
        "char-2": {"id": "char-2", "type": "character", "name": "미아", "sheet": "references/characters/char-2.png"},
    }
    scene = {"sceneNumber": 1, "character_ids": ["char-1", "char-2"], "location_id": "", "prop_ids": []}
    refs = scene_render.resolve_scene_refs(scene, ents, tmp_path)
    assert len(refs["character_sheets"]) == 1   # char-2 시트 파일 없음 → 제외
    assert refs["character_sheets"][0]["name"] == "하루"
    assert refs["location_sheet"] == {}
    assert refs["prop_sheets"] == []


def test_resolve_scene_refs_location_and_props(tmp_path):
    _mksheet(tmp_path, "references/locations/loc-1.png")
    _mksheet(tmp_path, "references/props/prop-1.png")
    ents = {
        "loc-1": {"id": "loc-1", "type": "location", "name": "거실", "sheet": "references/locations/loc-1.png"},
        "prop-1": {"id": "prop-1", "type": "prop", "name": "포스트잇", "sheet": "references/props/prop-1.png"},
    }
    scene = {"sceneNumber": 1, "character_ids": [], "location_id": "loc-1", "prop_ids": ["prop-1"]}
    refs = scene_render.resolve_scene_refs(scene, ents, tmp_path)
    assert refs["location_sheet"]["name"] == "거실"
    assert refs["prop_sheets"][0]["name"] == "포스트잇"


def test_build_scene_prompt_includes_scene_and_descriptors():
    p = scene_render.build_scene_prompt(
        {"image_prompt": "공원 산책"},
        ["1번 캐릭터 시트 '하루'", "인물 없음"],
        "STYLE", "scenes/scene_1.png")
    assert "공원 산책" in p
    assert "하루" in p
    assert "scenes/scene_1.png" in p
    assert "STYLE" in p
