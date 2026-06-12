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


def test_manifest_merges_motion(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "mo", "imageRef": "storyboard/sb.png"}])
    (d / "storyboard").mkdir()
    from PIL import Image
    Image.new("RGB", (100, 100)).save(d / "storyboard" / "sb.png")
    lay = d / "layers"; lay.mkdir()
    Image.new("RGBA", (100, 100)).save(lay / "mo__0_차.png")
    Image.new("RGBA", (100, 100)).save(lay / "mo__bg.png")
    (d / "motion_mo.json").write_text(json.dumps({
        "layers": [{"layer": "mo__0_차", "moves": [
            {"type": "pop", "start": 0.2, "duration": 0.6}]}],
        "camera": {"type": "pan_left", "amount": 40}}), encoding="utf-8")
    manifest.build_manifest(d)
    sc = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["scenes"][0]
    car = next(L for L in sc["layers"] if "차" in L["name"])
    assert car["moves"][0]["type"] == "pop"
    bg = next(L for L in sc["layers"] if L["kind"] == "bg")
    assert "moves" not in bg
    assert sc["camera"]["type"] == "pan_left"


def test_manifest_no_motion_file_ok(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "nm"}])
    manifest.build_manifest(d)
    sc = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["scenes"][0]
    assert "camera" not in sc                          # 모션 없으면 필드 자체 없음(하위호환)


def test_manifest_element_foot_point(tmp_path):
    """요소 레이어의 foot = 불투명 영역 하단 중앙(까딱 피벗)."""
    from PIL import Image
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "ft", "imageRef": "storyboard/sb.png"}])
    (d / "storyboard").mkdir(); Image.new("RGB", (200, 200)).save(d / "storyboard" / "sb.png")
    lay = d / "layers"; lay.mkdir()
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    for y in range(40, 160):                              # 인물: x 60~120, y 40~160
        for x in range(60, 120):
            im.putpixel((x, y), (200, 30, 40, 255))
    im.save(lay / "ft__0_인물.png")
    Image.new("RGBA", (200, 200), (10, 10, 10, 255)).save(lay / "ft__bg.png")
    manifest.build_manifest(d)
    sc = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["scenes"][0]
    el = next(L for L in sc["layers"] if L["kind"] == "element")
    assert el["foot"] == [90.0, 160.0]                    # bbox(60,40,120,160) 하단 중앙
    bg = next(L for L in sc["layers"] if L["kind"] == "bg")
    assert "foot" not in bg


def test_char_layer_auto_bob_without_plan(tmp_path):
    """_char 접미사(또는 kinds=character) 레이어는 모션 플랜 없이도 결정적 bob 부여."""
    from PIL import Image
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "ab", "imageRef": "storyboard/sb.png",
                          "duration_estimate_sec": 5}])
    (d / "storyboard").mkdir(); Image.new("RGB", (200, 200)).save(d / "storyboard" / "sb.png")
    lay = d / "layers"; lay.mkdir()
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    for y in range(50, 150):
        for x in range(80, 120):
            im.putpixel((x, y), (200, 30, 40, 255))
    im.save(lay / "ab__0_남자_char.png")                  # _char 접미사
    im.save(lay / "ab__1_책상.png")                       # 사물
    Image.new("RGBA", (200, 200), (9, 9, 9, 255)).save(lay / "ab__bg.png")
    manifest.build_manifest(d)                            # 모션 플랜 파일 없음
    sc = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["scenes"][0]
    char = next(L for L in sc["layers"] if "_char" in L["name"])
    assert char["moves"] == [{"type": "bob", "start": 0, "duration": 5.0}]   # 자동 bob
    desk = next(L for L in sc["layers"] if "책상" in L["name"])
    assert "moves" not in desk                            # 사물은 모션 없음


def test_char_auto_bob_not_duplicated_with_plan(tmp_path):
    """플랜에 이미 모션 있으면 자동 bob 중복 부여 안 함."""
    from PIL import Image
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "nb", "imageRef": "storyboard/sb.png"}])
    (d / "storyboard").mkdir(); Image.new("RGB", (100, 100)).save(d / "storyboard" / "sb.png")
    lay = d / "layers"; lay.mkdir()
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    im.putpixel((50, 50), (255, 0, 0, 255))
    im.save(lay / "nb__0_여자_char.png")
    (d / "motion_nb.json").write_text(json.dumps({
        "layers": [{"layer": "nb__0_여자_char", "moves": [
            {"type": "fade_in", "start": 0, "duration": 1},
            {"type": "bob", "start": 1, "duration": 2}]}],
        "camera": {"type": "none"}}), encoding="utf-8")
    manifest.build_manifest(d)
    sc = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["scenes"][0]
    char = next(L for L in sc["layers"] if "_char" in L["name"])
    # 캐릭터는 오퍼시티 금지 — fade_in 제거되고 bob만(중복 부여 없음), noFade 플래그
    assert [m["type"] for m in char["moves"]] == ["bob"]
    assert all(m.get("noFade") for m in char["moves"])


def test_manifest_layout_passthrough(tmp_path):
    """layout+데이터 통과, 비이미지 레이아웃 씬은 1920x1080 기본 컴프 + image None."""
    d = _proj(tmp_path, [
        {"sceneNumber": 1, "sceneId": "h", "narration": "n1", "layout": "headline_only",
         "headline": "큰 제목", "sub": "부제", "duration_estimate_sec": 4},
        {"sceneNumber": 2, "sceneId": "b", "narration": "n2", "layout": "bar",
         "headline": "비교", "chart": {"labels": ["A", "B"], "values": [10, 40], "unit": "%"}},
    ])
    manifest.build_manifest(d)
    mf = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    s1, s2 = mf["scenes"]
    assert s1["layout"] == "headline_only" and s1["headline"] == "큰 제목" and s1["sub"] == "부제"
    assert s1["image"] is None and s1["layers"] == []
    assert s1["width"] == 1920 and s1["height"] == 1080
    assert s2["layout"] == "bar" and s2["chart"]["values"] == [10, 40]
    assert "value" not in s2 and "quote_text" not in s2     # None 필드는 미포함
    assert Path(mf["ae_tokens"]).name == "ae_tokens.json" and Path(mf["ae_tokens"]).is_absolute()


def test_manifest_layout_defaults_cinematic(tmp_path):
    d = _proj(tmp_path, [{"sceneNumber": 1, "sceneId": "a", "imageRef": "storyboard/sb_a.png"}])
    (d / "storyboard").mkdir(); (d / "storyboard" / "sb_a.png").write_bytes(b"\x89PNG")
    manifest.build_manifest(d)
    sc = json.loads((d / "manifest.json").read_text(encoding="utf-8"))["scenes"][0]
    assert sc["layout"] == "cinematic"
    assert sc["image"].endswith("sb_a.png")
