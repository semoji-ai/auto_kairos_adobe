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
