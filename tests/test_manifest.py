import json
from pathlib import Path
from backend import manifest


def _proj(tmp_path, scenes_arr):
    d = tmp_path / "p"; d.mkdir()
    (d / "scenes.json").write_text(json.dumps({"scenes": scenes_arr}, ensure_ascii=False), encoding="utf-8")
    return d


def test_build_manifest_image_only(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a", "narration": "내레이션",
                          "imageRef": "storyboard/sb_a.png", "duration_estimate_sec": 4}])
    (d / "storyboard").mkdir(); (d / "storyboard" / "sb_a.png").write_bytes(b"\x89PNG")
    res = manifest.build_manifest(d)
    mf = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    assert res["scenes"] == 1 and Path(res["path"]).name == "manifest.json"
    sc = mf["scenes"][0]
    assert sc["image"].endswith("storyboard/sb_a.png") and Path(sc["image"]).is_absolute()
    assert sc["subtitle"] == "내레이션" and sc["duration"] == 4
    assert sc["layers"] == [] and sc["audio"] is None


def test_build_manifest_layers_bg_first(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "b", "imageRef": "storyboard/sb_b.png"}])
    (d / "storyboard").mkdir(); (d / "storyboard" / "sb_b.png").write_bytes(b"\x89PNG")
    lay = d / "layers"; lay.mkdir()
    (lay / "b__0_car.png").write_bytes(b"\x89PNG")
    (lay / "b__1_kid.png").write_bytes(b"\x89PNG")
    (lay / "b__bg.png").write_bytes(b"\x89PNG")
    sc = manifest.build_manifest(d)
    mf = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["scenes"][0]
    names = [Path(l["path"]).name for l in mf["layers"]]
    assert names[0] == "b__bg.png"                  # 배경이 배열 맨 앞(=AE 최하단)
    assert mf["layers"][0]["kind"] == "bg"
    assert set(names[1:]) == {"b__0_car.png", "b__1_kid.png"}


def test_build_manifest_audio_duration(tmp_path, monkeypatch):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "c", "narration": "n"}])
    (d / "audio").mkdir(); (d / "audio" / "tts_c.wav").write_bytes(b"x")
    monkeypatch.setattr(manifest.tts, "audio_duration", lambda p: 5.5)
    mf = json.loads((d / "manifest.json").read_text(encoding="utf-8")) if manifest.build_manifest(d) else {}
    sc = mf["scenes"][0]
    assert sc["audio"].endswith("audio/tts_c.wav") and sc["duration"] == 5.5


def test_build_manifest_duration_fallback(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "e"}])     # 오디오·duration 없음
    manifest.build_manifest(d)
    sc = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["scenes"][0]
    assert sc["duration"] == 3.0                    # 기본값


def test_build_manifest_only_scene(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a"},
                         {"sceneNumber": 2, "sceneId": "b"},
                         {"sceneNumber": 3, "sceneId": "c"}])
    res = manifest.build_manifest(d, only_scene=2)
    assert res["scenes"] == 1 and Path(res["path"]).name == "manifest_scene_2.json"
    mf = json.loads(Path(res["path"]).read_text(encoding="utf-8"))
    assert len(mf["scenes"]) == 1 and "_b" in mf["scenes"][0]["ae_comp_name"]
    # 전체 manifest.json은 건드리지 않음
    assert not (d / "manifest.json").exists()


def test_scene_layers_position_from_meta(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "z", "imageRef": "storyboard/sb_z.png"}])
    (d / "storyboard").mkdir()
    from PIL import Image
    Image.new("RGB", (1536, 1024)).save(d / "storyboard" / "sb_z.png")   # 컴프 크기 기준
    lay = d / "layers"; lay.mkdir()
    Image.new("RGBA", (100, 100)).save(lay / "z__0_car.png")             # 크롭된 요소
    Image.new("RGBA", (1536, 1024)).save(lay / "z__bg.png")
    (lay / "z__meta.json").write_text(
        '{"z__0_car.png":{"x":300,"y":200,"w":200,"h":160,"frame_w":1536,"frame_h":1024}}',
        encoding="utf-8")
    manifest.build_manifest(d)
    sc = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["scenes"][0]
    assert sc["width"] == 1536 and sc["height"] == 1024
    car = next(L for L in sc["layers"] if "car" in L["name"])
    assert car["position"] == [400.0, 280.0]      # 중심 (300+100, 200+80)
    assert car["scale"] == 100.0
    bg = next(L for L in sc["layers"] if L["kind"] == "bg")
    assert "position" not in bg                    # 배경은 풀프레임(좌표 없음)
