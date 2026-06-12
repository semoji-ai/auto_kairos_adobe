from pathlib import Path
from backend import imagegen


def test_versioned_path_first(tmp_path):
    p = imagegen.versioned_path(tmp_path, "ref_1.png")
    assert p.name == "ref_1.png"


def test_versioned_path_no_overwrite(tmp_path):
    (tmp_path / "ref_1.png").write_text("x", encoding="utf-8")
    p = imagegen.versioned_path(tmp_path, "ref_1.png")
    assert p.name == "ref_1_v2.png"
    (tmp_path / "ref_1_v2.png").write_text("x", encoding="utf-8")
    p2 = imagegen.versioned_path(tmp_path, "ref_1.png")
    assert p2.name == "ref_1_v3.png"


def test_is_rate_limited():
    assert imagegen.is_rate_limited("image_gen rate limit으로 실패") is True
    assert imagegen.is_rate_limited("OK 저장 완료") is False


def test_build_image_prompt():
    pr = imagegen.build_image_prompt("전기차 한 대", "STYLE_DESC", "images/ref_1.png")
    assert "STYLE_DESC" in pr
    assert "전기차 한 대" in pr
    assert "images/ref_1.png" in pr
    assert "image_gen" in pr


def test_build_image_prompt_nochar_forbids_base_person():
    pr = imagegen.build_image_prompt("전기차 충전 장면", "STYLE", "images/s1.png")
    assert "베이스의 인물" in pr and "포함하지 말" in pr
    assert "캐릭터 시트" not in pr


def test_build_image_prompt_character_branch():
    pr = imagegen.build_image_prompt("지오가 차를 가리킴", "STYLE", "images/s1.png",
                                     has_character_ref=True)
    assert "1번 캐릭터 시트" in pr and "100% 동일" in pr
    assert "세모지 베이스" in pr


def test_build_character_prompt_restyle():
    pr = imagegen.build_character_prompt("지오", "갈색 머리, 크림 셔츠", "characters/char_지오.png")
    assert "1번 이미지의 캐릭터를 '지오'" in pr
    assert "그대로 유지" in pr and "헤어와 의상만" in pr
    assert "characters/char_지오.png" in pr
    # 비율 텍스트 지시 금지 원칙이 프롬프트에 명시
    assert "비율을 텍스트로 새로 지정하지 말 것" in pr


def test_generate_one_attaches_base(tmp_path, monkeypatch):
    """character_ref 없으면 베이스만 첨부, has_character_ref=False로 빌드."""
    from backend import imagegen as ig
    seen = {}

    def fake_run(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        seen["images"] = images
        seen["prompt"] = prompt
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run)
    monkeypatch.setattr(ig, "base_img", lambda: tmp_path / "semoji_base.jpg")
    res = ig.generate_one(tmp_path, "ref_1.png", "전기차")
    assert res["status"] == "completed"
    assert seen["images"] == [str(tmp_path / "semoji_base.jpg")]
    assert "베이스의 인물" in seen["prompt"]


def test_generate_one_with_character_ref_order(tmp_path, monkeypatch):
    """character_ref 주면 [캐릭터, 베이스] 순서로 첨부 + 캐릭터 분기."""
    from backend import imagegen as ig
    seen = {}

    def fake_run(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        seen["images"] = images
        seen["prompt"] = prompt
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run)
    monkeypatch.setattr(ig, "base_img", lambda: tmp_path / "base.jpg")
    res = ig.generate_one(tmp_path, "s1.png", "지오가 차를 가리킴",
                          character_ref=str(tmp_path / "char_지오.png"))
    assert res["status"] == "completed"
    assert seen["images"] == [str(tmp_path / "char_지오.png"), str(tmp_path / "base.jpg")]
    assert "1번 캐릭터 시트" in seen["prompt"]


def test_generate_character_needs_base(tmp_path, monkeypatch):
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "base_img", lambda: None)
    res = ig.generate_character(tmp_path, "지오", "갈색 머리")
    assert res["status"] == "failed" and "semoji_base" in res["error"]


def test_generate_character_attaches_base(tmp_path, monkeypatch):
    from backend import imagegen as ig
    seen = {}

    def fake_run(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        seen["images"] = images
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run)
    monkeypatch.setattr(ig, "base_img", lambda: tmp_path / "base.jpg")
    res = ig.generate_character(tmp_path, "지오", "갈색 머리, 크림 셔츠")
    assert res["status"] == "completed"
    assert seen["images"] == [str(tmp_path / "base.jpg")]
    assert (tmp_path / "characters" / "char_지오.png").exists()


def test_versioned_path_in_subdir_concept(tmp_path):
    sb = tmp_path / "storyboard"; sb.mkdir()
    p = imagegen.versioned_path(sb, "sb_1.png")
    assert p.parent.name == "storyboard"
    assert p.name == "sb_1.png"


def test_build_layer_prompt_character():
    p = imagegen.build_layer_prompt("character", "STYLE", "char_1.png")
    assert "인물" in p and "마젠타" in p and "char_1.png" in p and "STYLE" in p


def test_build_layer_prompt_background():
    p = imagegen.build_layer_prompt("background", "STYLE", "bg_1.png")
    assert "배경" in p and "bg_1.png" in p
    assert "마젠타" not in p


def test_generate_many_runs_all(tmp_path, monkeypatch):
    from backend import imagegen as ig
    calls = []

    def fake_one(proj_dir, rel_out, image_prompt, *, subdir="images", **kw):
        calls.append(rel_out)
        out = proj_dir / subdir / rel_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG")
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "generate_one", fake_one)
    items = [("a.png", "p1"), ("b.png", "p2"), ("c.png", "p3")]
    results = ig.generate_many(tmp_path, items, subdir="storyboard", concurrency=3)
    assert len(results) == 3
    assert all(r["status"] == "completed" for r in results.values())
    assert set(calls) == {"a.png", "b.png", "c.png"}


def test_generate_many_concurrency_min_one(tmp_path, monkeypatch):
    from backend import imagegen as ig
    monkeypatch.setattr(ig, "generate_one",
                        lambda proj_dir, rel_out, p, **kw: {"status": "completed", "path": rel_out})
    results = ig.generate_many(tmp_path, [("a.png", "p")], concurrency=0)
    assert len(results) == 1


def test_build_element_layer_prompt():
    p = imagegen.build_element_layer_prompt("왼쪽 전기차", "프레임 왼쪽", "STYLE", "layers/x.png")
    assert "왼쪽 전기차" in p and "마젠타" in p and "#FF00FF" in p and "layers/x.png" in p
    assert "얹혀" in p          # 위에 얹힌 것 함께 그림(베이스 포함)


def test_build_element_layer_prompt_excludes_others():
    # 다른 선택 요소(문서)는 별도 레이어이므로 책상 레이어에서 제외
    p = imagegen.build_element_layer_prompt("책상", "중앙", "STYLE", "layers/d.png", others=["문서", "책상"])
    assert "별도 레이어" in p and "문서" in p
    # 자기 자신(책상)은 제외 목록에 안 들어감
    assert p.count("책상") >= 1


def test_analyze_scene_layers_parses(tmp_path, monkeypatch):
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir(); img = proj / "storyboard" / "s.png"; img.write_bytes(b"\x89PNG")

    def fake_run(prompt, cwd, *, output_schema=None, output_last=None, images=None, on_line=None, **kw):
        from pathlib import Path as _P
        _P(output_last).write_text('{"elements":[{"name":"전기차","location":"왼쪽"},'
                                   '{"name":"인물","location":"오른쪽"}]}', encoding="utf-8")
        return {"returncode": 0, "output_last": output_last}

    monkeypatch.setattr(ig.llm, "run_orchestrator", fake_run)
    res = ig.analyze_scene_layers(proj, str(img))
    assert [e["name"] for e in res["elements"]] == ["전기차", "인물"]


def test_analyze_scene_layers_prompt_uses_narration(tmp_path, monkeypatch):
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir(); img = proj / "storyboard" / "s.png"; img.write_bytes(b"\x89PNG")
    cap = {}

    def fake_run(prompt, cwd, *, output_schema=None, output_last=None, images=None, on_line=None, **kw):
        cap["prompt"] = prompt
        from pathlib import Path as _P
        _P(output_last).write_text('{"elements":[]}', encoding="utf-8")
        return {"returncode": 0, "output_last": output_last}

    monkeypatch.setattr(ig.llm, "run_orchestrator", fake_run)
    ig.analyze_scene_layers(proj, str(img), narration="아이가 전기차를 향해 달려간다", context="제목: 의미")
    assert "아이가 전기차를 향해 달려간다" in cap["prompt"]   # 내레이션 주입
    assert "캐릭터" in cap["prompt"]                          # 캐릭터 항상 분리 원칙
    assert "움직" in cap["prompt"]                            # 움직임 기반 선별


def test_split_scene_to_elements(tmp_path, monkeypatch):
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir(); img = proj / "storyboard" / "s.png"; img.write_bytes(b"\x89PNG")
    made = []

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        out.write_bytes(b"\x89PNG"); made.append(out.name)
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_magenta", lambda a, b: {"transparent_ratio": 0.5})
    res = ig.split_scene_to_elements(proj, str(img), "sid9",
                                     [{"name": "전기차", "location": "왼쪽"},
                                      {"name": "인물", "location": "오른쪽"}], concurrency=2)
    names = [r["rel"] for r in res["layers"]]
    # 요소 2개 + 배경 1개
    assert any("sid9__0" in n for n in names) and any("sid9__1" in n for n in names)
    assert any("sid9__bg" in n for n in names)


def test_chroma_key_magenta(tmp_path):
    from PIL import Image
    from backend import imagegen
    im = Image.new("RGBA", (4, 2), (255, 0, 255, 255))
    for y in range(2):
        im.putpixel((2, y), (30, 60, 200, 255))
        im.putpixel((3, y), (30, 60, 200, 255))
    src = tmp_path / "m.png"; im.save(src)
    out = tmp_path / "t.png"
    res = imagegen.chroma_key_magenta(src, out)
    from PIL import Image as I
    r = I.open(out).convert("RGBA")
    assert r.getpixel((0, 0))[3] == 0
    assert r.getpixel((3, 0))[3] == 255
    assert res["transparent_ratio"] > 0.4


def test_archive_prev_layers_moves_not_deletes(tmp_path):
    from backend import imagegen as ig
    lay = tmp_path / "layers"; lay.mkdir()
    (lay / "sid9__0_old.png").write_bytes(b"\x89PNG")
    (lay / "sid9__bg.png").write_bytes(b"\x89PNG")
    (lay / "other__0_x.png").write_bytes(b"\x89PNG")     # 다른 씬 — 유지
    moved = ig._archive_prev_layers(lay, "sid9")
    assert moved == 2
    assert not (lay / "sid9__0_old.png").exists()        # 활성 폴더에서 빠짐
    assert (lay / "_prev" / "sid9__0_old.png").exists()  # 보존됨(무삭제)
    assert (lay / "other__0_x.png").exists()             # 다른 씬 그대로


def test_normalize_layer_size_resizes(tmp_path):
    from PIL import Image
    from backend import imagegen as ig
    p = tmp_path / "L.png"
    Image.new("RGBA", (1672, 941), (255, 0, 0, 255)).save(p)   # codex 변칙 크기
    changed = ig.normalize_layer_size(p, (1536, 1024))
    assert changed is True
    assert Image.open(p).size == (1536, 1024)


def test_normalize_layer_size_noop_when_match(tmp_path):
    from PIL import Image
    from backend import imagegen as ig
    p = tmp_path / "L.png"
    Image.new("RGBA", (1536, 1024)).save(p)
    assert ig.normalize_layer_size(p, (1536, 1024)) is False    # 이미 일치 → 무변경


def test_split_normalizes_to_scene_size(tmp_path, monkeypatch):
    from PIL import Image
    from backend import imagegen as ig
    proj = tmp_path / "p"; proj.mkdir()
    (proj / "storyboard").mkdir()
    scene = proj / "storyboard" / "s.png"
    Image.new("RGB", (1536, 1024)).save(scene)                  # 씬 = 1536x1024

    def fake_run_codex(proj_dir, out, prompt, *, images=None, retries=2, on_line=None, post=None):
        Image.new("RGBA", (1672, 941), (0, 255, 0, 255)).save(out)   # 변칙 크기로 생성
        if post: post(out)
        return {"status": "completed", "path": str(out)}

    monkeypatch.setattr(ig, "_run_codex_image", fake_run_codex)
    monkeypatch.setattr(ig, "chroma_key_magenta", lambda a, b: {"transparent_ratio": 0.5})
    res = ig.split_scene_to_elements(proj, str(scene), "sz1",
                                     [{"name": "차", "location": "왼쪽"}], concurrency=1)
    for r in res["layers"]:
        assert Image.open(proj / r["rel"]).size == (1536, 1024)  # 요소+배경 모두 씬 크기


def _mk_magenta_test_img(tmp_path):
    """중앙 빨강 사각형 + 마젠타 배경 + 경계 혼합색 1px 띠."""
    from PIL import Image
    im = Image.new("RGB", (100, 100), (255, 0, 255))          # 순수 마젠타
    for y in range(30, 70):
        for x in range(30, 70):
            im.putpixel((x, y), (200, 30, 40))                # 요소(빨강)
    for x in range(29, 71):                                    # 경계 혼합(반쯤 마젠타)
        im.putpixel((x, 29), (228, 15, 148)); im.putpixel((x, 70), (228, 15, 148))
    p = tmp_path / "m.png"; im.save(p)
    return p


def test_soft_chroma_core_kept_bg_removed(tmp_path):
    from PIL import Image
    from backend import imagegen as ig
    p = _mk_magenta_test_img(tmp_path)
    r = ig.chroma_key_magenta(p, p)
    out = Image.open(p).convert("RGBA")
    assert out.getpixel((50, 50))[3] == 255                   # 요소 중심 불투명
    assert out.getpixel((5, 5))[3] == 0                       # 마젠타 배경 완전 투명
    assert 0.5 < r["transparent_ratio"] < 0.95                # 비율 신호 유지


def test_soft_chroma_edge_soft_alpha(tmp_path):
    from PIL import Image
    from backend import imagegen as ig
    p = _mk_magenta_test_img(tmp_path)
    ig.chroma_key_magenta(p, p)
    out = Image.open(p).convert("RGBA")
    a = out.getpixel((50, 29))[3]                              # 혼합 경계 픽셀
    assert a < 255                                             # 이진(255)이 아니라 소프트
