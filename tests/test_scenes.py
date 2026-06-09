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
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "aaa11111", "title": "A",
                          "narration": "가", "image_prompt": "장면1"}])
    (d / "storyboard").mkdir(); (d / "storyboard" / "sb_aaa11111.png").write_bytes(b"\x89PNG")
    (d / "layers").mkdir()
    (d / "layers" / "bg_aaa11111.png").write_bytes(b"\x89PNG")
    (d / "layers" / "char_aaa11111.png").write_bytes(b"\x89PNG")
    data = scenes.load_scenes(d)
    s = data["scenes"][0]
    assert s["_image"] == "storyboard/sb_aaa11111.png"
    assert s["_layers"] == ["layers/bg_aaa11111.png", "layers/char_aaa11111.png"]
    assert data["dir"] == str(d)


def test_load_scenes_picks_latest_image_version(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 2, "sceneId": "bbb22222", "image_prompt": "x"}])
    sb = d / "storyboard"; sb.mkdir()
    (sb / "sb_bbb22222.png").write_bytes(b"\x89PNG")
    (sb / "sb_bbb22222_v2.png").write_bytes(b"\x89PNG")
    s = scenes.load_scenes(d)["scenes"][0]
    assert s["_image"] == "storyboard/sb_bbb22222_v2.png"


def test_load_scenes_latest_version_numeric_sort(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 5, "sceneId": "ccc55555", "image_prompt": "x"}])
    sb = d / "storyboard"; sb.mkdir()
    for nm in ("sb_ccc55555.png", "sb_ccc55555_v2.png", "sb_ccc55555_v3.png", "sb_ccc55555_v10.png"):
        (sb / nm).write_bytes(b"\x89PNG")
    s = scenes.load_scenes(d)["scenes"][0]
    assert s["_image"] == "storyboard/sb_ccc55555_v10.png"


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


def test_ensure_scene_ids_assigns_and_persists(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "image_prompt": "x"},
                         {"sceneNumber": 2, "image_prompt": "y"}])
    scenes.ensure_scene_ids(d)
    saved = json.loads((d / "scenes.json").read_text(encoding="utf-8"))["scenes"]
    sids = [s["sceneId"] for s in saved]
    assert all(sids) and len(set(sids)) == 2          # 발급 + 고유
    # 멱등: 재호출해도 sceneId 불변
    scenes.ensure_scene_ids(d)
    saved2 = json.loads((d / "scenes.json").read_text(encoding="utf-8"))["scenes"]
    assert [s["sceneId"] for s in saved2] == sids


def test_ensure_scene_ids_migrates_number_assets(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "image_prompt": "x"}])
    sb = d / "storyboard"; sb.mkdir()
    (sb / "sb_1.png").write_bytes(b"IMG")
    (sb / "sb_1_v2.png").write_bytes(b"IMG2")
    lay = d / "layers"; lay.mkdir()
    (lay / "bg_1.png").write_bytes(b"BG"); (lay / "char_1.png").write_bytes(b"CH")
    scenes.ensure_scene_ids(d)
    sid = json.loads((d / "scenes.json").read_text(encoding="utf-8"))["scenes"][0]["sceneId"]
    # 번호 에셋이 sid 기반으로 복사됨(무삭제 — 원본도 남음)
    assert (sb / f"sb_{sid}.png").read_bytes() == b"IMG"
    assert (sb / f"sb_{sid}_v2.png").read_bytes() == b"IMG2"
    assert (lay / f"bg_{sid}.png").read_bytes() == b"BG"
    assert (lay / f"char_{sid}.png").read_bytes() == b"CH"
    assert (sb / "sb_1.png").exists()   # 원본 보존(무삭제)


def test_scene_id_for(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 5, "image_prompt": "x"}])
    scenes.ensure_scene_ids(d)
    sid = scenes.scene_id_for(d, 5)
    assert sid and scenes.scene_id_for(d, 99) is None
