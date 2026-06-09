import json
from pathlib import Path
from backend import scenes


def _proj(tmp_path, scene_list):
    d = tmp_path / "p"; d.mkdir()
    (d / "scenes.json").write_text(
        json.dumps({"project_id": "p", "scenes": scene_list}, ensure_ascii=False),
        encoding="utf-8")
    return d


def test_load_scenes_enriches_media_and_layers(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "title": "A", "narration": "가",
                          "image_prompt": "장면1"}])
    (d / "storyboard").mkdir(); (d / "storyboard" / "sb_1.png").write_bytes(b"\x89PNG")
    (d / "layers").mkdir()
    (d / "layers" / "bg_1.png").write_bytes(b"\x89PNG")
    (d / "layers" / "char_1.png").write_bytes(b"\x89PNG")
    data = scenes.load_scenes(d)
    s = data["scenes"][0]
    assert s["_image"] == "storyboard/sb_1.png"
    assert s["_layers"] == ["layers/bg_1.png", "layers/char_1.png"]
    assert data["dir"] == str(d)


def test_load_scenes_picks_latest_image_version(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 2, "image_prompt": "x"}])
    sb = d / "storyboard"; sb.mkdir()
    (sb / "sb_2.png").write_bytes(b"\x89PNG")
    (sb / "sb_2_v2.png").write_bytes(b"\x89PNG")
    s = scenes.load_scenes(d)["scenes"][0]
    assert s["_image"] == "storyboard/sb_2_v2.png"   # 최신 버전


def test_load_scenes_latest_version_numeric_sort(tmp_path):
    # v10은 v2/v3보다 뒤(숫자 정렬). 사전식이면 v10이 v2 앞에 와서 v3을 최신으로 잘못 고름.
    d = _proj(tmp_path, [{"sceneNumber": 5, "image_prompt": "x"}])
    sb = d / "storyboard"; sb.mkdir()
    for nm in ("sb_5.png", "sb_5_v2.png", "sb_5_v3.png", "sb_5_v10.png"):
        (sb / nm).write_bytes(b"\x89PNG")
    s = scenes.load_scenes(d)["scenes"][0]
    assert s["_image"] == "storyboard/sb_5_v10.png"


def test_load_scenes_no_media(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "image_prompt": "x"}])
    s = scenes.load_scenes(d)["scenes"][0]
    assert s["_image"] is None and s["_layers"] == []


def test_load_scenes_missing_file(tmp_path):
    assert scenes.load_scenes(tmp_path / "nope") == {"scenes": [], "dir": ""}


def test_update_narration_sets_dirty(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "narration": "옛", "image_prompt": "x"}])
    res = scenes.update_narration(d, 1, "새 나레이션")
    assert res == {"ok": True, "sceneNumber": 1}
    saved = json.loads((d / "scenes.json").read_text(encoding="utf-8"))
    assert saved["scenes"][0]["narration"] == "새 나레이션"
    assert saved["scenes"][0]["narration_dirty"] is True


def test_update_narration_unknown_scene(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "image_prompt": "x"}])
    assert "error" in scenes.update_narration(d, 99, "x")
